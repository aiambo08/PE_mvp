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
# System prompt with anti-hallucination constraints and financial precision
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a Senior Advisor and Lead Financial Due Diligence Auditor for Private Equity Investment Committees.
Your objective is to answer analyst inquiries in a precise, structured, exhaustive manner grounded EXCLUSIVELY in the provided document context.

═══════════════════════════════════════════════════════
FINANCIAL AUDIT GUIDELINES (M&A)
═══════════════════════════════════════════════════════

1. DOCUMENTARY ACCURACY:
   - Base your responses solely on the data, tables, financial statements, and clauses present in the context.
   - Always quote exact figures, fiscal years (FY2023, FY2024, FY2025, etc.), percentages, and add-backs exactly as they appear.

2. AUDIT CITATIONS:
   - Always cite the source page number for every key financial figure or relevant clause (e.g. [Page 1], [Page 2]).

3. FINANCIAL STATEMENT RIGOR:
   - Clearly distinguish between Revenue/Sales, Gross Margin, Reported EBITDA vs. Normalized/Adjusted EBITDA, Net Debt, and bank covenants.
   - If extraordinary expenses or EBITDA adjustments (add-backs) are detailed, explain them clearly.

4. TRANSPARENCY ON MISSING DATA:
   - If a specific metric or clause does not appear in the analyzed documents, state this explicitly with professional rigor without inventing figures.
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

        # 3.2 If still no documents in database
        if not search_results:
            return RAGQueryResponse(
                query=request.query,
                answer=(
                    "No indexed documents found in the Data Room. "
                    "Please upload a Memorandum (CIM or Audit in PDF) and index it before executing queries."
                ),
                citations=[],
                retrieval_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        # 4. Build citations and context blocks
        citations: list[SourceCitation] = []
        context_blocks: list[str] = []

        for hit in search_results:
            payload = hit.payload or {}

            # Robust text extraction
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

            filename = payload.get("filename") or node_metadata.get("filename", "Document")
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
                f"[Source: {filename}, Page {page_number}]\n{window_text}"
            )

        context_str = "\n\n---\n\n".join(context_blocks)

        # 5. Structured analysis prompt for LLM
        user_prompt = (
            f"DATA ROOM DOCUMENTATION:\n"
            f"{context_str}\n\n"
            f"════════════════════════════════════\n"
            f"DUE DILIGENCE ANALYST QUESTION:\n"
            f"{request.query}\n\n"
            f"Please respond clearly, directly, and exhaustively, citing exact figures and page numbers in English."
        )

        # 6. LLM generation (temperature 0.0 for maximum determinism)
        try:
            completion = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
            answer = completion.choices[0].message.content or "No response generated."
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
                f"[LLM ERROR] Could not connect to model at {provider_info}. "
                f"Please verify {settings.LLM_PROVIDER} is running: {type(e).__name__}"
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return RAGQueryResponse(
            query=request.query,
            answer=answer,
            citations=citations,
            retrieval_time_ms=round(elapsed_ms, 2),
        )