import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.scrapers.company_scraper import CompanyWebScraper
from app.services.extraction_service import CompanyExtractionService

logger = logging.getLogger(__name__)

# Directorio de resultados inicializado una sola vez (no en el hot path del endpoint)
RESULTS_DIR = Path("data/processed_json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # os.makedirs movido aquí: se ejecuta una sola vez al arrancar el servidor
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    app.state.scraper = CompanyWebScraper(
        headless=settings.SCRAPER_HEADLESS,
        timeout=settings.SCRAPER_TIMEOUT,
    )
    app.state.extractor = CompanyExtractionService()
    logger.info("Services initialized.")
    yield
    logger.info("Shutting down.")


app = FastAPI(title="PE Deal Sourcing API", version="0.2.0", lifespan=lifespan)


class AnalyzeCompanyRequest(BaseModel):
    url: str


@app.post("/api/v1/analyze-company")
async def analyze_company(request: AnalyzeCompanyRequest) -> dict:
    scraper: CompanyWebScraper = app.state.scraper
    extractor: CompanyExtractionService = app.state.extractor

    raw_data = await scraper.scrape_company(request.url)
    if raw_data.scrape_status != "SUCCESS":
        raise HTTPException(status_code=400, detail=f"Scraping fallido: {raw_data.error_message}")

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

    return analysis_result
