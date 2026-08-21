from dataclasses import dataclass
from app.models.structured_schemas import (
    StructuredCompanyProfile, BusinessModelType, CompanyScaleCategory,
)
from app.models.scoring_schemas import (
    SCORING_CRITERIA, SCALE_ORDER, InvestmentMandateConfig,
)


@dataclass
class ScoringResult:
    """Typed output for scoring results."""
    total_score: float
    tier: str
    score_breakdown: dict


class PEScoringEngine:
    """Deterministic, stateless scoring engine (legacy static weights). No external I/O."""

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
        score_digital = min(score_digital, 15)
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


class DynamicPEScoringEngine:
    """
    Motor de scoring dinamico con seleccion de criterios y filtros eliminatorios.

    Proceso:
      1. Knockout Check — si el target incumple un filtro duro, es Tier 3 directo.
      2. Normalizacion de Pesos — los pesos de los criterios activos se ajustan a 100.
      3. Calculo Ponderado — suma de (raw_score * peso_normalizado) por criterio activo.
      4. Asignacion de Tier — Tier 1 (>=75), Tier 2 (50-74), Tier 3 (<50).
    """

    @staticmethod
    def calculate_from_mandate(profile: dict, mandate: InvestmentMandateConfig) -> dict:
        """
        Recalcula el score PE segun el mandato activo.

        Args:
            profile: dict serializado de StructuredCompanyProfile (tal como viene de la API).
            mandate: InvestmentMandateConfig con criterios activos, pesos y filtros knockout.

        Returns:
            dict con total_score, tier, score_breakdown y knocked_out flag.
        """
        knocked_out = False
        knockout_reason: str | None = None

        # ── STEP 1: Knockout Check ─────────────────────────────────────────
        if mandate.knockout_b2b:
            bm = profile.get("business_model", "UNKNOWN")
            if bm in ("B2C", "UNKNOWN"):
                knocked_out = True
                knockout_reason = f"Model '{bm}' excluded (mandatory B2B filter)"

        if not knocked_out and mandate.knockout_min_scale:
            scale = profile.get("estimated_scale", "UNKNOWN")
            min_idx = SCALE_ORDER.index(mandate.knockout_min_scale) if mandate.knockout_min_scale in SCALE_ORDER else 0
            curr_idx = SCALE_ORDER.index(scale) if scale in SCALE_ORDER else len(SCALE_ORDER) - 1
            # UNKNOWN (last index) should also fail the knockout
            if scale == "UNKNOWN" or curr_idx < min_idx:
                knocked_out = True
                knockout_reason = f"Scale '{scale}' below required minimum '{mandate.knockout_min_scale}'"

        if knocked_out:
            return {
                "total_score": 0.0,
                "tier": "TIER_3_DISCARD",
                "score_breakdown": {},
                "knocked_out": True,
                "knockout_reason": knockout_reason,
            }

        # ── PASO 2: Normalizacion de Pesos ────────────────────────────────
        active_raw_weights = {k: mandate.weights.get(k, 0.0) for k in mandate.active_criteria}
        total_raw = sum(active_raw_weights.values())
        if total_raw <= 0:
            total_raw = 1.0  # fallback defensivo
        normalized: dict[str, float] = {k: (v / total_raw) * 100.0 for k, v in active_raw_weights.items()}

        # ── PASO 3: Calculo Ponderado ─────────────────────────────────────
        breakdown: dict[str, float] = {}
        for key in mandate.active_criteria:
            criterion = SCORING_CRITERIA.get(key)
            if not criterion:
                continue
            raw = criterion["extractor"](profile)
            weighted = raw * normalized[key]
            label = criterion["label"]
            breakdown[label] = round(weighted, 1)

        total = round(sum(breakdown.values()), 1)
        total = max(0.0, min(100.0, total))

        # ── PASO 4: Asignacion de Tier ────────────────────────────────────
        tier = (
            "TIER_1_HIGH_PRIORITY" if total >= 75
            else "TIER_2_QUALIFIED" if total >= 50
            else "TIER_3_DISCARD"
        )

        return {
            "total_score": total,
            "tier": tier,
            "score_breakdown": breakdown,
            "knocked_out": False,
            "knockout_reason": None,
        }
