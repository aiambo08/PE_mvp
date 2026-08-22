import json
import logging
import shutil, os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import aiofiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.config import settings
from app.scrapers.company_scraper import CompanyWebScraper
from app.services.extraction_service import CompanyExtractionService

from app.models.rag_schemas import DocumentUploadResponse, RAGQueryRequest, RAGQueryResponse
from app.models.financial_schemas import SensitivityMatrixResponse
from app.models.scoring_schemas import InvestmentMandateConfig
from app.services.document_service import DocumentIngestionService
from app.services.rag_service import FinancialRAGService
from app.services.financial_simulation_service import FinancialStressEngine
from app.services.scoring_service import DynamicPEScoringEngine
from app.services.report_service import ICReportGenerator



logger = logging.getLogger(__name__)

# Rutas absolutas independientes del CWD
BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "data" / "processed_json"
UPLOAD_PDFS_DIR = BASE_DIR / "data" / "uploaded_pdfs"
QDRANT_DB_DIR = BASE_DIR / "data" / "qdrant_db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_PDFS_DIR.mkdir(parents=True, exist_ok=True)
    QDRANT_DB_DIR.mkdir(parents=True, exist_ok=True)

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
    """Returns complete list of analyzed targets from disk repository."""
    results = []
    if RESULTS_DIR.exists():
        for file in RESULTS_DIR.glob("*.json"):
            try:
                content = file.read_text(encoding="utf-8")
                data = json.loads(content)
                if data.get("status") == "SUCCESS":
                    results.append(data)
            except Exception as e:
                logger.warning("Error reading result file '%s': %r", file.name, e)
    return results

@app.get("/api/v1/companies/{domain}/teaser-pdf")
async def get_company_teaser_pdf(domain: str):
    """
    Generates and returns the Investment Teaser PDF from the backend.
    """
    file_path = RESULTS_DIR / f"{domain}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Target company not found.")

    data = json.loads(file_path.read_text(encoding="utf-8"))

    pdf_output_path = f"data/reports/{domain}_one_pager.pdf"
    
    # Delegate generation to report service
    ICReportGenerator.generate_one_pager_pdf(
        domain=domain,
        profile=data.get("profile", {}),
        scoring=data.get("scoring", {}),
        output_path=pdf_output_path,
        contact_email=data.get("contact_email"),
        social_links=data.get("social_links", []),
    )

    return FileResponse(
        path=pdf_output_path,
        filename=f"IC_Teaser_{domain}.pdf",
        media_type="application/pdf"
    )


@app.post("/api/v1/recalculate-scores")
async def recalculate_scores(mandate: InvestmentMandateConfig) -> List[dict]:
    """
    Recalculates PE Target Score for all stored targets on disk using the provided mandate.
    Requires no scraping or LLM calls. Deterministic sub-100ms response.
    """
    results = []
    if RESULTS_DIR.exists():
        for file in RESULTS_DIR.glob("*.json"):
            try:
                content = file.read_text(encoding="utf-8")
                data = json.loads(content)
                if data.get("status") != "SUCCESS":
                    continue
                profile = data.get("profile", {})
                dyn_scoring = DynamicPEScoringEngine.calculate_from_mandate(profile, mandate)
                results.append({
                    "domain": data.get("domain"),
                    "profile": profile,
                    "scoring": dyn_scoring,
                    "contact_email": data.get("contact_email"),
                    "social_links": data.get("social_links", []),
                })
            except Exception as e:
                logger.warning("Error recalculating score for '%s': %r", file.name, e)
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
    force_refresh: bool = False  # When True, bypasses cache and re-scrapes + re-extracts

@app.post("/api/v1/simulate-leverage", response_model=SensitivityMatrixResponse)
async def simulate_leverage(req: StressSimulationRequest):
    """Executes financial covenants and LBO solvency stress sensitivity analysis."""
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


def _normalize_domain_string(url_or_domain: str) -> str:
    """Normalizes URL or domain string into a clean lowercase domain key."""
    raw = url_or_domain.strip().lower()
    if "://" not in raw:
        raw = f"https://{raw}"
    from urllib.parse import urlparse
    parsed = urlparse(raw)
    domain = parsed.netloc or parsed.path
    if ":" in domain:
        domain = domain.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.strip("/")


@app.post("/api/v1/analyze-company")
async def analyze_company(request: AnalyzeCompanyRequest):
    scraper: CompanyWebScraper = app.state.scraper
    extractor: CompanyExtractionService = app.state.extractor

    try:
        # ── Cache check: return stored result if fresh ────────────────────
        _cache_domain = _normalize_domain_string(request.url)
        _cache_path = RESULTS_DIR / f"{_cache_domain}.json"

        if not request.force_refresh and _cache_path.exists():
            age_hours = (time.time() - _cache_path.stat().st_mtime) / 3600
            if age_hours < settings.CACHE_TTL_HOURS:
                logger.info(
                    "Cache hit for '%s' (age: %.1fh < TTL: %.1fh). Returning stored result.",
                    _cache_domain, age_hours, settings.CACHE_TTL_HOURS,
                )
                async with aiofiles.open(_cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.loads(await f.read())
                if cached_data.get("status") == "SUCCESS":
                    return JSONResponse(content=cached_data)

        # ── Full pipeline: scrape + extract + score ───────────────────────
        raw_data = await scraper.scrape_company(request.url)
        if raw_data.scrape_status == "FAILED":
            raise HTTPException(
                status_code=400,
                detail=f"Scraping failed: {raw_data.error_message or 'Could not access the website.'}"
            )

        analysis_result = await extractor.extract_and_score(raw_data)

        if analysis_result.get("status") in {"EXTRACTION_ERROR", "LLM_VALIDATION_ERROR"}:
            logger.error("Analysis failed for %s: %s", request.url, analysis_result.get("error"))
            raise HTTPException(
                status_code=502,
                detail=f"LLM Extraction failed: {analysis_result.get('error')}",
            )

        # Async I/O — does not block asyncio event loop
        norm_domain = _normalize_domain_string(raw_data.company_domain)
        analysis_result["domain"] = norm_domain
        file_path = RESULTS_DIR / f"{norm_domain}.json"
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
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

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
        logger.exception("app.state.ingestion unavailable — lifespan failed to initialize: %r", e)
        raise HTTPException(status_code=503, detail=f"Service not initialized: {repr(e)}")
    except Exception as e:
        logger.exception("Error in upload_document for '%s': %r", file.filename, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")
    finally:
        temp_path.unlink(missing_ok=True)

@app.post("/api/v1/query-rag", response_model=RAGQueryResponse)
async def query_rag(request: RAGQueryRequest):
    rag_service: FinancialRAGService = app.state.rag
    try:
        return await rag_service.query_due_diligence(request)
    except Exception as e:
        logger.exception("Error processing RAG query: %r", e)
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")