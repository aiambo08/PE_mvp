import logging
import instructor
from openai import AsyncOpenAI

from app.config import settings
from app.models.raw_schemas import RawCompanyData
from app.models.structured_schemas import StructuredCompanyProfile
from app.services.scoring_service import PEScoringEngine

logger = logging.getLogger(__name__)

_MAX_MAIN_CHARS = 8_000
_MAX_SUB_CHARS = 2_000
_MAX_SUBPAGES = 3
_MAX_TOTAL_CHARS = 16_000


class CompanyExtractionService:
    """Servicio de extracción LLM apuntando a Ollama local con instructor."""

    def __init__(self) -> None:
        # Mode.JSON es el correcto para el endpoint /v1/chat/completions de Ollama.
        # JSON_SCHEMA requiere soporte nativo del backend que Ollama no tiene.
        self.client = instructor.from_openai(
            AsyncOpenAI(
                base_url=settings.OLLAMA_BASE_URL,
                api_key="ollama",  # Ignorado por Ollama, requerido por el SDK
            ),
            mode=instructor.Mode.JSON,
        )
        self.model = settings.LOCAL_LLM_MODEL

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
                            "Eres un analista de datos de M&A. "
                            "Genera extracciones estrictamente en JSON válido siguiendo el schema indicado."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Analiza el texto de la empresa '{raw_data.company_domain}' "
                            f"y extrae la información requerida.\n\n"
                            f"TEXTO DE LA EMPRESA:\n{context_text}"
                        ),
                    },
                ],
            )
        except Exception:
            # logger.exception preserva el stack trace completo en los logs de Uvicorn
            logger.exception("LLM extraction failed for %s", raw_data.company_domain)
            return {
                "domain": raw_data.company_domain,
                "status": "EXTRACTION_ERROR",
                "error": "LLM extraction failed — see server logs for details",
            }

        scoring_results = PEScoringEngine.calculate_score(profile)
        return {
            "domain": raw_data.company_domain,
            "status": "SUCCESS",
            "profile": profile.model_dump(),
            "scoring": scoring_results,
            "contact_email": raw_data.contact_email,
        }