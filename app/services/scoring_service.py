from dataclasses import dataclass
from app.models.structured_schemas import (
    StructuredCompanyProfile, BusinessModelType, CompanyScaleCategory,
)


@dataclass
class ScoringResult:
    """Typed output for scoring results."""
    total_score: float
    tier: str
    score_breakdown: dict


class PEScoringEngine:
    """Deterministic, stateless scoring engine. No external I/O."""

    @staticmethod
    def calculate_score(profile: StructuredCompanyProfile) -> dict:
        score = 0.0
        breakdown: dict[str, float] = {}

        # 1. Modelo de negocio (MAX 30)
        bm_scores: dict[BusinessModelType, float] = {
            BusinessModelType.B2B_SAAS: 30,
            BusinessModelType.INDUSTRIAL_MANUFACTURING: 28,
            BusinessModelType.LOGISTICS_DISTRIBUTION: 25,
            BusinessModelType.B2B_SERVICES: 22,
            BusinessModelType.B2B_PRODUCT: 18,
            BusinessModelType.MIXED: 12,
            BusinessModelType.B2C: 5,
            BusinessModelType.UNKNOWN: 0,
        }
        score_bm = bm_scores.get(profile.business_model, 0)
        breakdown["business_model"] = score_bm
        score += score_bm

        # 2. Escala (MAX 25)
        scale_scores: dict[CompanyScaleCategory, float] = {
            CompanyScaleCategory.MEDIUM_BUSINESS: 25,
            CompanyScaleCategory.SMALL_BUSINESS: 18,
            CompanyScaleCategory.LARGE_BUSINESS: 14,
            CompanyScaleCategory.EXTRA_LARGE_BUSINESS: 10,
            CompanyScaleCategory.MICRO_ENTERPRISE: 5,
            CompanyScaleCategory.UNKNOWN: 0,
        }
        score_scale = scale_scores.get(profile.estimated_scale, 0)
        breakdown["scale_score"] = score_scale
        score += score_scale

        # 3. Transformación digital (MAX 15)
        dd = profile.digital_signals
        score_digital = sum([
            8 if dd.has_client_portal else 0,
            7 if dd.modern_tech_stack else 0,
            5 if dd.has_e_commerce else 0,
            2 if dd.active_hiring_signals else 0,
        ])
        score_digital = min(score_digital, 15)  # 🟡 FIX 9: cap al máximo documentado
        breakdown["digital_score"] = score_digital
        score += score_digital

        # 4. Tesis M&A y Relevo Generacional (MAX 30)
        score_thesis = (
            (15 if profile.investment_thesis.buy_and_build_potential else 0)
            + (15 if profile.is_family_owned_or_founder_led else 0)
        )
        breakdown["thesis_score"] = score_thesis
        score += score_thesis

        final_score = round(max(0.0, min(100.0, score)), 2)
        tier = (
            "TIER_1_HIGH_PRIORITY" if final_score >= 75
            else "TIER_2_QUALIFIED" if final_score >= 50
            else "TIER_3_DISCARD"
        )
        return {"total_score": final_score, "tier": tier, "score_breakdown": breakdown}
