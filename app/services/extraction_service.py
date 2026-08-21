import logging
import instructor
from openai import AsyncOpenAI
from typing import Any, Dict, Tuple

from app.config import settings
from app.models.raw_schemas import RawCompanyData
from app.models.structured_schemas import StructuredCompanyProfile
from app.services.scoring_service import PEScoringEngine

logger = logging.getLogger(__name__)

_MAX_MAIN_CHARS = 8_000
_MAX_SUB_CHARS = 2_000
_MAX_SUBPAGES = 3
_MAX_TOTAL_CHARS = 16_000

# ── Anti-Hallucination System Prompt ─────────────────────────────────────────
# Explicitly instructs the LLM to ground ALL extracted fields in the scraped
# text. Prevents fabricated names like "Tech Innovations Inc." that occur when
# Ollama silently truncates context and the model falls back to training priors.
_EXTRACTION_SYSTEM_PROMPT = (
    "You are a Senior Private Equity Investment Director conducting M&A target screening.\n"
    "You MUST extract a structured company profile from the scraped website text provided.\n\n"
    "GROUNDING RULES:\n"
    "1. company_name: Extract the EXACT commercial name from the website or domain.\n"
    "   NEVER invent names. NEVER use placeholders like 'Tech Innovations Inc.' or 'ExampleTech'.\n"
    "   If unclear, use the domain name itself.\n"
    "2. core_activity: Describe what the company ACTUALLY does based on the text.\n"
    "   Focus on their main product/service offering, not press releases or partnerships.\n"
    "3. business_model: CLASSIFY based on textual evidence. Use your PE expertise:\n"
    "   - B2B_SAAS: Cloud platform, API, subscription SaaS for businesses\n"
    "   - B2B_PRODUCT: Software or product sold to businesses (non-SaaS)\n"
    "   - B2B_SERVICES: Consulting, outsourcing, professional services\n"
    "   - INDUSTRIAL_MANUFACTURING: Physical goods manufacturing\n"
    "   - LOGISTICS_DISTRIBUTION: Supply chain, warehousing, transport\n"
    "   - B2C: Consumer-facing product or service\n"
    "   - MIXED: Clear mix of B2B and B2C\n"
    "   - UNKNOWN: Only if truly impossible to determine\n"
    "4. target_sectors: Infer from the text which industries the company serves.\n"
    "5. Boolean fields (is_family_owned_or_founder_led, has_recurring_revenue_signals,\n"
    "   has_industry_certifications, digital_signals.*): Set to true ONLY with\n"
    "   explicit textual evidence. Default to false or null when uncertain.\n"
    "6. estimated_scale: Set to UNKNOWN unless headcount data is explicitly mentioned.\n"
    "7. Do NOT hallucinate facts not present in the text. Conservative defaults are\n"
    "   preferred over inventive guesses for factual fields.\n"
)


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


def _build_ollama_extra_body() -> Dict[str, Any]:
    """
    Construye los parámetros extra para Ollama que previenen truncamiento
    silencioso de contexto y fuerzan generación determinista.

    CRÍTICO: Sin num_ctx explícito, Ollama usa 2048 tokens por defecto.
    El prompt total (schema JSON + texto scrapeado) supera 5500 tokens,
    causando truncamiento silencioso → el LLM alucina arquetipos genéricos.
    """
    return {
        "options": {
            "num_ctx": settings.LLM_NUM_CTX,   # 16384 — prevents silent truncation
            "seed": settings.LLM_SEED,          # 42 — deterministic token sampling
            "temperature": 0.0,                 # Greedy decoding at Ollama level
            "top_p": 0.1,                       # Near-greedy nucleus sampling
        }
    }


class CompanyExtractionService:
    """Servicio de extracción LLM multi-proveedor (Gemini, OpenAI, Ollama) con instructor."""

    def __init__(self) -> None:
        self.client, self.model = _build_instructor_client()
        self._is_ollama = settings.LLM_PROVIDER not in ("gemini", "openai")
        logger.info(
            "CompanyExtractionService inicializado [Provider: %s, Model: %s, NumCtx: %s]",
            settings.LLM_PROVIDER,
            self.model,
            settings.LLM_NUM_CTX if self._is_ollama else "N/A (cloud)",
        )

    def _prepare_prompt_text(self, raw_data: RawCompanyData) -> str:
        """Constructs prompt context with defensive truncation to protect VRAM and context limits."""
        parts = [
            f"--- MAIN PAGE ({raw_data.main_page.url}) ---\n"
            f"{raw_data.main_page.raw_text[:_MAX_MAIN_CHARS]}"
        ]
        for page in raw_data.internal_pages[:_MAX_SUBPAGES]:
            parts.append(
                f"--- SUBPAGE ({page.url}) ---\n"
                f"{page.raw_text[:_MAX_SUB_CHARS]}"
            )
        return "\n\n".join(parts)[:_MAX_TOTAL_CHARS]

    async def extract_and_score(self, raw_data: RawCompanyData) -> dict:
        """Extracts structured profile with LLM and computes deterministic PE scoring."""
        if raw_data.scrape_status != "SUCCESS":
            return {
                "domain": raw_data.company_domain,
                "status": "FAILED",
                "error": raw_data.error_message,
            }

        context_text = self._prepare_prompt_text(raw_data)

        # Build provider-specific kwargs for determinism
        extra_kwargs: Dict[str, Any] = {}
        if self._is_ollama:
            extra_kwargs["extra_body"] = _build_ollama_extra_body()

        try:
            profile: StructuredCompanyProfile = await self.client.chat.completions.create(
                model=self.model,
                response_model=StructuredCompanyProfile,
                max_retries=3,
                temperature=0.0,  # Greedy decoding — true determinism (was 0.1)
                messages=[
                    {
                        "role": "system",
                        "content": _EXTRACTION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Target Domain: '{raw_data.company_domain}'\n\n"
                            f"Extract the structured investment profile from the following "
                            f"scraped website content. Ground ALL fields in the text below.\n\n"
                            f"SCRAPED CONTENT:\n{context_text}"
                        ),
                    },
                ],
                **extra_kwargs,
            )
        except Exception as e:
            logger.exception("LLM extraction failure for domain %s: %r", raw_data.company_domain, e)
            return {
                "domain": raw_data.company_domain,
                "status": "EXTRACTION_ERROR",
                "error": f"LLM Failure ({type(e).__name__}): verify {settings.LLM_PROVIDER} service",
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