from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, UTC


class DocumentUploadResponse(BaseModel):
    document_id: str = Field(description="UUID único del documento almacenado")
    filename: str
    company_domain: str
    total_pages: int
    chunks_indexed: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RAGQueryRequest(BaseModel):
    query: str = Field(description="Pregunta en lenguaje natural sobre la due diligence")
    company_domain: str | None = Field(
        default=None,
        description="Filtro opcional para acotar la búsqueda a un target específico"
    )
    top_k: int = Field(default=6, ge=1, le=20, description="Número de fragmentos relevantes a recuperar")


class SourceCitation(BaseModel):
    document_id: str
    filename: str
    page_number: int
    score: float = Field(description="Puntuación de similitud semántica")
    excerpt: str = Field(description="Texto exacto recuperado de la fuente")


class RAGQueryResponse(BaseModel):
    query: str
    answer: str = Field(description="Respuesta generada por el LLM respaldada en los documentos")
    citations: List[SourceCitation] = Field(description="Referencias exactas de página y texto fuente")  # plural
    retrieval_time_ms: float