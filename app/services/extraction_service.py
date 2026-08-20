import logging
import instructor
from openai import AsyncOpenAI
from typing import Any, Tuple

from app.config import settings
from app.models.raw_schemas import RawCompanyData
from app.models.structured_schemas import StructuredCompanyProfile
from app.services.scoring_service import PEScoringEngine

logger = logging.getLogger(__name__)

_MAX_MAIN_CHARS = 8_000
_MAX_SUB_CHARS = 2_000
_MAX_SUBPAGES = 3
_MAX_TOTAL_CHARS = 16_000

def _build_instructor_client() -> Tuple[Any, str]:
    """Construye el cliente instructor según LLM_PROVIDER configurado."""
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError("LLM_PROVIDER=gemini configurado pero falta GEMINI_API_KEY en .env")
        raw_client = AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.GEMINI_API_KEY,
        )
        return (
            instructor.from_openai(raw_client, mode=instructor.Mode.JSON),
            settings.GEMINI_MODEL,
        )
    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER=openai configurado pero falta OPENAI_API_KEY en .env")
        raw_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return (
            instructor.from_openai(raw_client, mode=instructor.Mode.TOOLS),
            settings.OPENAI_MODEL,
        )
    else:  # Ollama por defecto
        raw_client = AsyncOpenAI(
            base_url=settings.OLLAMA_BASE_URL,
            api_key="ollama",
        )
        return (
            instructor.from_openai(raw_client, mode=instructor.Mode.JSON),
            settings.LOCAL_LLM_MODEL,
        )


class CompanyExtractionService:
    """Servicio de extracción LLM multi-proveedor (Gemini, OpenAI, Ollama) con instructor."""

    def __init__(self) -> None:
        self.client, self.model = _build_instructor_client()
        logger.info(
            "CompanyExtractionService inicializado [Provider: %s, Model: %s]",
            settings.LLM_PROVIDER,
            self.model,
        )

    def _prepare_prompt_text(self, raw_data: RawCompanyData) -> str:
        """Construye el contexto con truncado defensivo para proteger la VRAM."""
        parts = [
            f"--- PÁGINA PRINCIPAL ({raw_data.main_page.url}) ---\n"
            f"{raw_data.main_page.raw_text[:_MAX_MAIN_CHARS]}"
        ]
        # Limitar número de subpáginas + tamaño por subpágina
        for page in raw_data.internal_pages[:_MAX_SUBPAGES]:
            parts.append(
                f"--- SUBPÁGINA ({page.url}) ---\n"
                f"{page.raw_text[:_MAX_SUB_CHARS]}"
            )
        return "\n\n".join(parts)[:_MAX_TOTAL_CHARS]

    async def extract_and_score(self, raw_data: RawCompanyData) -> dict:
        """Extrae perfil estructurado con el LLM y aplica el scoring PE determinista."""
        if raw_data.scrape_status != "SUCCESS":
            return {
                "domain": raw_data.company_domain,
                "status": "FAILED",
                "error": raw_data.error_message,
            }

        context_text = self._prepare_prompt_text(raw_data)

        try:
            # temperature es parámetro estándar OpenAI — NO usar extra_body["options"]
            # que pertenece a la API nativa de Ollama (/api/generate) y es ignorado aquí.
            profile: StructuredCompanyProfile = await self.client.chat.completions.create(
                model=self.model,
                response_model=StructuredCompanyProfile,
                max_retries=3,
                temperature=0.1,  # Determinismo máximo para extracción JSON
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un Director de Inversiones de Private Equity especializado en M&A. "
                            "Analiza la información corporativa y extrae estrictamente el perfil estructurado "
                            "conforme al esquema JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Analiza el texto de la empresa con dominio '{raw_data.company_domain}' "
                            f"y elabora el perfil de inversión.\n\n"
                            f"CONTENIDO EXTRAÍDO:\n{context_text}"
                        ),
                    },
                ],
            )
        except Exception as e:
            # logger.exception preserva el stack trace completo en los logs de Uvicorn
            logger.exception("Fallo en extracción LLM para el dominio %s: %r", raw_data.company_domain, e)
            return {
                "domain": raw_data.company_domain,
                "status": "EXTRACTION_ERROR",
                "error": f"Fallo LLM ({type(e).__name__}): verifique el servicio {settings.LLM_PROVIDER}",
            }

        scoring_results = PEScoringEngine.calculate_score(profile)
        return {
            "domain": raw_data.company_domain,
            "status": "SUCCESS",
            "profile": profile.model_dump(mode="json"),
            "scoring": scoring_results,
            "contact_email": raw_data.contact_email,
            "social_links": raw_data.social_links,
        }