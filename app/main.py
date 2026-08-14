import json
import logging
import shutil, os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles
from fastapi import FastAPI, UploadFile, File, Form,HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.config import settings
from app.scrapers.company_scraper import CompanyWebScraper
from app.services.extraction_service import CompanyExtractionService

from app.models.rag_schemas import DocumentUploadResponse, RAGQueryRequest, RAGQueryResponse
from app.models.financial_schemas import SensitivityMatrixResponse
from app.services.document_service import DocumentIngestionService
from app.services.rag_service import FinancialRAGService
from app.services.financial_simulation_service import FinancialStressEngine


logger = logging.getLogger(__name__)

# Directorio de resultados inicializado una sola vez (no en el hot path del endpoint)
RESULTS_DIR = Path("data/processed_json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    Path("data/uploaded_pdfs").mkdir(parents=True, exist_ok=True)
    Path("data/qdrant_db").mkdir(parents=True, exist_ok=True)

    app.state.scraper = CompanyWebScraper(headless=settings.SCRAPER_HEADLESS, timeout=settings.SCRAPER_TIMEOUT)
    app.state.extractor = CompanyExtractionService()

    try:
        logger.info("Inicializando DocumentIngestionService...")
        ingestion = DocumentIngestionService()
        app.state.ingestion = ingestion
        logger.info("DocumentIngestionService OK. Qdrant tipo: %s", type(ingestion.qdrant_client).__name__)

        logger.info("Inicializando FinancialRAGService...")
        app.state.rag = FinancialRAGService(
            qdrant_client=ingestion.qdrant_client,
            embed_model=ingestion.embed_model
        )
        logger.info("FinancialRAGService OK. EmbedModel compartido: %s", ingestion.embed_model is app.state.rag.embed_model)
    except Exception as exc:
        logger.exception("ERROR CRITICO en lifespan al inicializar servicios RAG: %r", exc)
        raise  # re-lanzar para que uvicorn registre el fallo de arranque

    logger.info("Todos los servicios inicializados correctamente.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="PE Deal Sourcing & Due Diligence API",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/companies")
async def list_analyzed_companies():
    """Retorna la lista completa de empresas analizadas sin acoplamiento a disco en la UI."""
    results = []
    if RESULTS_DIR.exists():
        for file in RESULTS_DIR.glob("*.json"):
            try:
                async with aiofiles.open(file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                    if data.get("status") == "SUCCESS":
                        results.append(data)
            except Exception as e:
                logger.warning("Error leyendo archivo de resultado '%s': %r", file.name, e)
    return results


class StressSimulationRequest(BaseModel):
    revenue: float
    ebitda: float
    net_debt: float
    max_covenant_ratio: float = 3.0
    fixed_cost_ratio: float = 0.60
    annual_debt_service: float | None = None


class AnalyzeCompanyRequest(BaseModel):
    url: str

@app.post("/api/v1/simulate-leverage", response_model=SensitivityMatrixResponse)
async def simulate_leverage(req: StressSimulationRequest):
    """Ejecuta el análisis de estrés de covenants financieros y solvencia LBO."""
    try:
        data = FinancialStressEngine.run_sensitivity_matrix(
            revenue=req.revenue,
            ebitda=req.ebitda,
            net_debt=req.net_debt,
            max_covenant_ratio=req.max_covenant_ratio,
            fixed_cost_ratio=req.fixed_cost_ratio,
            annual_debt_service=req.annual_debt_service,
        )
        return SensitivityMatrixResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/analyze-company")
async def analyze_company(request: AnalyzeCompanyRequest):
    scraper: CompanyWebScraper = app.state.scraper
    extractor: CompanyExtractionService = app.state.extractor

    try:
        raw_data = await scraper.scrape_company(request.url)
        if raw_data.scrape_status == "FAILED":
            raise HTTPException(
                status_code=400,
                detail=f"Scraping fallido: {raw_data.error_message or 'No se pudo acceder a la página web.'}"
            )

        analysis_result = await extractor.extract_and_score(raw_data)

        if analysis_result.get("status") in {"EXTRACTION_ERROR", "LLM_VALIDATION_ERROR"}:
            logger.error("Analysis failed for %s: %s", request.url, analysis_result.get("error"))
            raise HTTPException(
                status_code=502,
                detail=f"Extracción LLM fallida: {analysis_result.get('error')}",
            )

        # I/O asíncrono — no bloquea el event loop de asyncio
        file_path = RESULTS_DIR / f"{raw_data.company_domain}.json"
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(analysis_result, ensure_ascii=False, indent=2))

        # JSONResponse explícito para evitar revalidación de FastAPI sobre el dict
        return JSONResponse(content=analysis_result)

    except HTTPException:
        raise  # re-lanzar HTTPExceptions (400, 502) sin capturarlas
    except Exception as e:
        logger.exception("Unexpected error processing %s: %r", request.url, e)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {type(e).__name__}: {repr(e)}")


@app.post("/api/v1/upload-document", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), company_domain: str = Form(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    temp_dir = Path("data/uploaded_pdfs")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename

    content = await file.read()
    async with aiofiles.open(temp_path, "wb") as buffer:
        await buffer.write(content)

    try:
        ingestion_service: DocumentIngestionService = app.state.ingestion
        result = await ingestion_service.process_and_index_pdf(
            file_path=str(temp_path),
            filename=file.filename,
            company_domain=company_domain
        )
        return result
    except AttributeError as e:
        logger.exception("app.state.ingestion no disponible — lifespan falló al inicializar: %r", e)
        raise HTTPException(status_code=503, detail=f"Servicio no inicializado: {repr(e)}")
    except Exception as e:
        logger.exception("Error en upload_document para '%s': %r", file.filename, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")
    finally:
        temp_path.unlink(missing_ok=True)

@app.post("/api/v1/query-rag", response_model=RAGQueryResponse)
async def query_financial_rag(request: RAGQueryRequest):
    rag_service: FinancialRAGService = app.state.rag
    return await rag_service.query_due_diligence(request)

    