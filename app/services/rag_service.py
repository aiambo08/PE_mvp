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
Eres un Asesor Senior y Auditor Principal de Due Diligence Financiera para Comités de Inversión de Private Equity.
Tu objetivo es responder a las preguntas del analista de manera precisa, estructurada, exhaustiva y fundamentada EXCLUSIVAMENTE en el contexto documental proporcionado.

═══════════════════════════════════════════════════════
DIRECTRICES DE AUDITORÍA FINANCIERA (M&A)
═══════════════════════════════════════════════════════

1. FIDELIDAD DOCUMENTAL:
   - Basa tus respuestas únicamente en los datos, tablas, estados financieros y cláusulas presentes en el contexto.
   - Cita siempre las cifras exactas, ejercicios fiscales (FY2023, FY2024, FY2025, etc.), porcentajes y add-backs tal como aparecen.

2. CITAS DE AUDITORÍA:
   - Menciona el número de página de procedencia de cada dato financiero clave o cláusula relevante (ej. [Pág. 1], [Pág. 2]).

3. RIGOR EN TABLAS Y ESTADOS FINANCIEROS:
   - Distingue con precisión entre Ingresos/Ventas, Margen Bruto, EBITDA Reportado vs. EBITDA Normalizado/Ajustado, Deuda Financiera Neta y Covenants bancarios.
   - Si se detallan gastos extraordinarios o ajustes de EBITDA (add-backs), explícalos claramente.

4. TRANSPARENCIA ANTE DATOS AUSENTES:
   - Si una métrica o dato específico no aparece en los documentos analizados, acláralo expresamente con rigor profesional sin inventar cifras.
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

        # Singleton de embeddings multilingüe — coherente con DocumentIngestionService
        self.embed_model = embed_model or HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small")

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

        # 2. Filtro por empresa objetivo (aislamiento de Data Room si se especifica)
        query_filter = None
        target_domain = (request.company_domain or "").strip().lower()
        if target_domain and target_domain not in {"all", "todos", "global"}:
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

        # 3.1 Si no hay resultados con filtro de dominio, reintentar globalmente
        if not search_results and query_filter is not None:
            logger.info("Sin resultados para dominio '%s', ejecutando búsqueda global en Data Room...", target_domain)
            search_results = await loop.run_in_executor(
                None,
                lambda: self.qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=request.top_k,
                ),
            )

        # 3.2 Si aún no hay documentos en la base de datos
        if not search_results:
            return RAGQueryResponse(
                query=request.query,
                answer=(
                    "No se encontraron documentos indexados en el Data Room. "
                    "Por favor, sube un Memorandum (CIM o Auditoría en PDF) e indexalo antes de realizar consultas."
                ),
                citations=[],
                retrieval_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        # 4. Construir citas y bloques de contexto
        citations: list[SourceCitation] = []
        context_blocks: list[str] = []

        for hit in search_results:
            payload = hit.payload or {}

            # Extracción robusta de texto
            window_text = (
                payload.get("text")
                or payload.get("window")
                or payload.get("original_text")
                or ""
            )

            # Fallback: LlamaIndex node content JSON
            node_metadata = {}
            if "_node_content" in payload:
                try:
                    node_data = _json.loads(payload["_node_content"])
                    if not window_text:
                        window_text = node_data.get("text", "")
                    node_metadata = node_data.get("metadata", {})
                except (ValueError, TypeError):
                    pass

            if not window_text:
                window_text = str(payload)

            filename = payload.get("filename") or node_metadata.get("filename", "Documento")
            page_number = int(payload.get("page_number") or node_metadata.get("page_number", 1))

            citations.append(
                SourceCitation(
                    document_id=str(payload.get("document_id") or node_metadata.get("document_id", "N/A")),
                    filename=str(filename),
                    page_number=page_number,
                    score=round(float(hit.score), 4),
                    excerpt=str(window_text)[:300],
                )
            )
            context_blocks.append(
                f"[Fuente: {filename}, Pág. {page_number}]\n{window_text}"
            )

        context_str = "\n\n---\n\n".join(context_blocks)

        # 5. Prompt de análisis estructurado para el LLM
        user_prompt = (
            f"DOCUMENTACIÓN DEL DATA ROOM:\n"
            f"{context_str}\n\n"
            f"════════════════════════════════════\n"
            f"PREGUNTA DEL ANALISTA DE DUE DILIGENCE:\n"
            f"{request.query}\n\n"
            f"Por favor, responde de forma clara, directa y fundamentada citando las cifras y páginas exactas."
        )

        # 6. Generación LLM (temperatura 0.0 para máximo determinismo)
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