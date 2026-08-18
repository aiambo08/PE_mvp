import asyncio
import json as _json
import logging
import time
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.config import settings
from app.models.rag_schemas import RAGQueryRequest, RAGQueryResponse, SourceCitation
from app.services.document_service import create_qdrant_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt con restricciones anti-alucinación de precisión financiera
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
Eres un Auditor Principal de Due Diligence Financiera para operaciones de Private Equity.
Tu único objetivo es responder preguntas basándote EXCLUSIVAMENTE en el contexto proporcionado.

═══════════════════════════════════════════════════════
REGLAS DE ORO — INCUMPLIRLAS INVALIDA TU ANÁLISIS
═══════════════════════════════════════════════════════

1. SOLO CONTEXTO: Responde únicamente con información extraída literalmente del CONTEXTO.
   Nunca uses conocimiento externo ni rellenes huecos con estimaciones.

2. INFORMACIÓN INSUFICIENTE: Si el contexto no contiene datos suficientes para responder
   con certeza, responde exactamente con esta frase y nada más:
   "INFORMACIÓN INSUFICIENTE EN LOS DOCUMENTOS ANALIZADOS."

3. PROHIBICIÓN ABSOLUTA DE CÁLCULOS INVENTADOS:
   - NO realices divisiones ni operaciones matemáticas a menos que el resultado
     esté explícitamente escrito en el contexto.
   - Si ves "Ventas: 4.200 k€" y "EBITDA: 630 k€", NO calcules el margen tú mismo.
     Solo cítalo si el porcentaje aparece explícitamente en el texto o tabla.

4. TABLAS Y COLUMNAS: Lee con precisión las cabeceras de columna.
   Nunca confundas "Margen Bruto %" con "EBITDA %", ni "Ingresos" con "Ventas netas".

5. CITAS OBLIGATORIAS: Cada dato financiero citado debe ir acompañado de su fuente
   en el formato exacto: [Fuente: {filename}, Pág. {page_number}]

6. CONCENTRACIÓN DE CLIENTES: Si el contexto menciona porcentajes de facturación
   por cliente, verifica la columna antes de asignar el % al cliente correcto.

7. CIFRAS EXACTAS: Respeta las unidades (k€, M€, %) y el ejercicio fiscal (FY2023/24/25)
   tal como aparecen. No redondees ni conviertas unidades.

8. CONCISIÓN TÉCNICA: Sé directo y preciso. Sin introducciones, sin resúmenes
   ni frases como "según el contexto proporcionado…". Ve al dato.
""".strip()


# ---------------------------------------------------------------------------
# Factory del cliente LLM (ollama / gemini / openai)
# ---------------------------------------------------------------------------

def _build_llm_client() -> tuple[Any, str]:
    """Construye el cliente LLM según LLM_PROVIDER configurado en settings."""
    provider = settings.LLM_PROVIDER

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError("LLM_PROVIDER=gemini pero GEMINI_API_KEY no configurado en .env")
        from openai import AsyncOpenAI
        return (
            AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=settings.GEMINI_API_KEY,
            ),
            settings.GEMINI_MODEL,
        )

    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER=openai pero OPENAI_API_KEY no configurado en .env")
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY), settings.OPENAI_MODEL

    else:  # ollama (default)
        from openai import AsyncOpenAI
        return (
            AsyncOpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama"),
            settings.LOCAL_LLM_MODEL,
        )


# ---------------------------------------------------------------------------
# Servicio RAG de Due Diligence
# ---------------------------------------------------------------------------

class FinancialRAGService:
    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        embed_model: HuggingFaceEmbedding | None = None,
    ):
        # Reutiliza el QdrantClient del DocumentIngestionService si se inyecta
        self.qdrant_client = qdrant_client or create_qdrant_client()
        self.collection_name = "pe_due_diligence"

        # Singleton de embeddings — evita doble carga del modelo en RAM
        self.embed_model = embed_model or HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

        # Cliente LLM según configuración
        self.openai_client, self.model = _build_llm_client()
        logger.info(
            "FinancialRAGService — provider='%s', model='%s'",
            settings.LLM_PROVIDER, self.model,
        )

    async def query_due_diligence(self, request: RAGQueryRequest) -> RAGQueryResponse:
        start_time = time.time()
        loop = asyncio.get_running_loop()

        # 1. Embedding de la query (CPU-bound → thread pool)
        query_vector = await loop.run_in_executor(
            None, self.embed_model.get_query_embedding, request.query
        )

        # 2. Filtro estricto por empresa objetivo (Aislamiento Multi-Target M&A)
        if not request.company_domain or not request.company_domain.strip():
            raise ValueError(
                "Fallo de Seguridad / Auditoría: Debe especificarse un 'company_domain' "
                "para aislar el Data Room y evitar fugas de información confidencial entre targets."
            )
        target_domain = request.company_domain.strip().lower()
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="company_domain",
                    match=qmodels.MatchValue(value=target_domain),
                )
            ]
        )

        # 3. Búsqueda vectorial (QdrantClient síncrono → thread pool)
        search_results = await loop.run_in_executor(
            None,
            lambda: self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=request.top_k,
            ),
        )

        # 3.1 Verificación defensiva de documentos existentes para este target
        if not search_results:
            return RAGQueryResponse(
                query=request.query,
                answer=(
                    f"INFORMACIÓN INSUFICIENTE: No se encontraron documentos indexados "
                    f"en el Data Room para el target '{target_domain}'."
                ),
                citations=[],
                retrieval_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        # 4. Construir citas y bloques de contexto con ventana completa
        citations: list[SourceCitation] = []
        context_blocks: list[str] = []

        for hit in search_results:
            payload = hit.payload or {}

            # SentenceWindowNodeParser guarda el texto expandido en "window",
            # y el fragmento original en "original_text". Prioridad: window > text.
            window_text = (
                payload.get("window")
                or payload.get("original_text")
                or payload.get("text")
                or ""
            )

            # Fallback: LlamaIndex puede serializar el nodo en "_node_content" (JSON)
            if not window_text:
                raw_content = payload.get("_node_content")
                if raw_content:
                    try:
                        node_data = _json.loads(raw_content)
                        window_text = node_data.get("text", "")
                    except (ValueError, TypeError):
                        window_text = str(raw_content)

            if not window_text:
                logger.warning(
                    "Payload sin texto recuperable — hit id=%s, doc=%s, keys=%s",
                    hit.id, payload.get("document_id", "?"), list(payload.keys()),
                )

            citations.append(
                SourceCitation(
                    document_id=payload.get("document_id", "N/A"),
                    filename=payload.get("filename", "N/A"),
                    page_number=int(payload.get("page_number", 1)),
                    score=round(hit.score, 4),
                    excerpt=str(window_text)[:300],
                )
            )
            context_blocks.append(
                f"[Fuente: {payload.get('filename', 'N/A')}, "
                f"Pág. {payload.get('page_number', '?')}]\n{window_text}"
            )

        context_str = "\n\n---\n\n".join(context_blocks)

        # 5. Prompt con razonamiento guiado (CoT) para evitar cálculos inventados
        user_prompt = (
            f"CONTEXTO FINANCIERO RECUPERADO:\n"
            f"{context_str}\n\n"
            f"════════════════════════════════════\n"
            f"INSTRUCCIÓN DE RAZONAMIENTO:\n"
            f"Antes de responder, localiza EXPLÍCITAMENTE en el contexto la frase o celda\n"
            f"que contiene el dato solicitado. Si no la encuentras, declara INFORMACIÓN INSUFICIENTE.\n"
            f"════════════════════════════════════\n\n"
            f"PREGUNTA DEL ANALISTA:\n{request.query}"
        )

        # 6. Generación LLM (temperatura 0 = máximo determinismo)
        try:
            completion = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
            answer = completion.choices[0].message.content or "Sin respuesta generada."
        except Exception as e:
            provider_info = (
                settings.OLLAMA_BASE_URL
                if settings.LLM_PROVIDER == "ollama"
                else settings.LLM_PROVIDER
            )
            logger.error(
                "Error LLM provider='%s' (%s): %s",
                settings.LLM_PROVIDER, provider_info, e,
            )
            answer = (
                f"[ERROR LLM] No se pudo conectar al modelo en {provider_info}. "
                f"Verifica que {settings.LLM_PROVIDER} esté corriendo: {type(e).__name__}"
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return RAGQueryResponse(
            query=request.query,
            answer=answer,
            citations=citations,
            retrieval_time_ms=round(elapsed_ms, 2),
        )