import asyncio
import logging
import uuid
from pathlib import Path

import pdfplumber
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from llama_index.core import Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.config import settings
from app.models.rag_schemas import DocumentUploadResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Qdrant client factory — intenta servidor remoto, cae a in-memory si falla
# ---------------------------------------------------------------------------

def create_qdrant_client() -> QdrantClient:
    """
    Intenta conectar al servidor Qdrant remoto.
    Si no está disponible, usa almacenamiento en memoria (compatible con uvicorn --reload).

    NOTA: ':memory:' no persiste datos entre reinicios.
    Para persistencia: docker run -p 6333:6333 qdrant/qdrant
    """
    try:
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3)
        client.get_collections()  # Prueba de conectividad
        logger.info("Conectado a Qdrant remoto en %s:%s", settings.QDRANT_HOST, settings.QDRANT_PORT)
        return client
    except Exception as e:
        logger.warning(
            "Qdrant remoto no disponible (%s). "
            "Usando modo en memoria. Los datos NO persisten entre reinicios. "
            "Para persistencia: docker run -p 6333:6333 qdrant/qdrant",
            type(e).__name__,
        )
        return QdrantClient(":memory:")


# ---------------------------------------------------------------------------
# Extracción estructurada de PDF con preservación de tablas
# ---------------------------------------------------------------------------

def _extract_pdf_with_tables(file_path: str) -> list[dict]:
    """
    Extrae texto de cada página preservando tablas en formato Markdown.

    Ventajas sobre PDFReader (pdfminer):
    - pdfplumber detecta celdas de tabla con coordenadas precisas.
    - Las tablas se convierten a Markdown pipes para que el LLM las entienda.
    - Evita mezclar texto de tabla con texto de párrafo en el mismo bloque.
    """
    extracted_pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # Texto no-tabular de la página
            text_body = page.extract_text() or ""

            # Tablas detectadas → Markdown
            tables = page.extract_tables()
            table_md = ""
            for table in tables:
                rows_md = []
                is_first_row = True
                for row in table:
                    cleaned = [str(cell).replace("\n", " ").strip() if cell else "" for cell in row]
                    rows_md.append("| " + " | ".join(cleaned) + " |")
                    if is_first_row:
                        # Añadir separador de encabezado Markdown
                        rows_md.append("| " + " | ".join(["---"] * len(cleaned)) + " |")
                        is_first_row = False
                table_md += "\n".join(rows_md) + "\n\n"

            full_content = f"{text_body}\n\n{table_md}".strip() if table_md else text_body.strip()
            extracted_pages.append({
                "page_number": i + 1,
                "content": full_content,
            })

    return extracted_pages


# ---------------------------------------------------------------------------
# Servicio de ingesta de documentos
# ---------------------------------------------------------------------------

from llama_index.core.node_parser import SentenceSplitter
from qdrant_client.http.models import PointStruct

class DocumentIngestionService:
    def __init__(self, embed_model: HuggingFaceEmbedding | None = None):
        # 1. Cliente Qdrant (remoto o in-memory — decidido en runtime)
        self.qdrant_client = create_qdrant_client()
        self.collection_name = "pe_due_diligence"
        self._ensure_collection_exists()

        # 2. Modelo de embeddings multilingüe optimizado para español e inglés financiero
        self.embed_model = embed_model or HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small")

        # 3. Chunking con preservación de tablas y bloques financieros íntegros
        self.node_parser = SentenceSplitter(
            chunk_size=800,
            chunk_overlap=150,
        )

    def _ensure_collection_exists(self) -> None:
        """Crea la colección Qdrant con las dimensiones correctas si no existe."""
        existing = {c.name for c in self.qdrant_client.get_collections().collections}
        if self.collection_name not in existing:
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=384,                          # multilingual-e5-small → 384 dims
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info("Colección '%s' creada en Qdrant (384d, Cosine).", self.collection_name)

    async def process_and_index_pdf(
        self, file_path: str, filename: str, company_domain: str
    ) -> DocumentUploadResponse:
        """
        Pipeline completo:
        1. Extracción estructurada con pdfplumber (tablas → Markdown)
        2. Parseo en nodos conservando bloques semánticos y estados contables
        3. Pre-cómputo de embeddings en thread pool
        4. Upsert a Qdrant (sin bloquear el event loop)
        """
        loop = asyncio.get_running_loop()

        # 1. Extracción PDF — I/O bound y CPU moderado → thread pool
        pages_data = await loop.run_in_executor(
            None, lambda: _extract_pdf_with_tables(file_path)
        )

        # UUID completo (no truncado) para garantizar unicidad cross-colección
        doc_id = str(uuid.uuid4())

        # 2. Construir documentos LlamaIndex con metadatos de auditoría
        documents = []
        for page in pages_data:
            if not page["content"]:
                logger.warning("Página %d sin contenido en '%s' — omitida.", page["page_number"], filename)
                continue
            documents.append(
                Document(
                    text=page["content"],
                    metadata={
                        "document_id": doc_id,
                        "filename": filename,
                        "company_domain": company_domain,
                        "page_number": page["page_number"],
                    },
                    # Excluir metadatos del texto que se indexa para no contaminar embeddings
                    excluded_embed_metadata_keys=["document_id", "company_domain"],
                    excluded_llm_metadata_keys=["document_id"],
                )
            )

        # 3. Parseo en nodos con SentenceWindow — CPU-bound → thread pool
        nodes = await loop.run_in_executor(
            None, lambda: self.node_parser.get_nodes_from_documents(documents)
        )

        logger.info(
            "Indexando '%s' — %d págs., %d nodos — dominio: '%s'",
            filename, len(pages_data), len(nodes), company_domain,
        )

        # 4. Pre-computar embeddings en thread pool para evitar conflictos de event loop
        #    cuando VectorStoreIndex intente llamar al modelo desde un hilo secundario.
        def compute_and_assign_embeddings() -> None:
            for node in nodes:
                node.embedding = self.embed_model.get_text_embedding(node.get_content())

        await loop.run_in_executor(None, compute_and_assign_embeddings)

        # 5. Limpieza previa de fragmentos existentes para garantizar idempotencia
        try:
            await loop.run_in_executor(
                None,
                lambda: self.qdrant_client.delete(
                    collection_name=self.collection_name,
                    points_selector=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="company_domain",
                                match=qmodels.MatchValue(value=company_domain),
                            ),
                            qmodels.FieldCondition(
                                key="filename",
                                match=qmodels.MatchValue(value=filename),
                            ),
                        ]
                    ),
                ),
            )
            logger.info("Limpieza previa completada para '%s' en dominio '%s'.", filename, company_domain)
        except Exception as del_exc:
            logger.debug("Limpieza previa en Qdrant omitida o sin registros previos: %r", del_exc)

        # 6. Upsert directo a Qdrant con IDs deterministas para evitar duplicidad acumulativa
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{company_domain}:{filename}:{i}")),
                vector=node.embedding,
                payload={
                    "document_id": doc_id,
                    "filename": filename,
                    "company_domain": company_domain,
                    "page_number": int(node.metadata.get("page_number", 1)),
                    "text": node.get_content(),
                },
            )
            for i, node in enumerate(nodes)
        ]
        await loop.run_in_executor(
            None,
            lambda: self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points,
            ),
        )
        logger.info(
            "Upsert completado — %d puntos en colección '%s' para dominio '%s'.",
            len(points), self.collection_name, company_domain,
        )

        return DocumentUploadResponse(
            document_id=doc_id,
            filename=filename,
            company_domain=company_domain,
            total_pages=len(pages_data),
            chunks_indexed=len(nodes),
        )