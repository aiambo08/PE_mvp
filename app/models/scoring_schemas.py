from __future__ import annotations

from typing import Callable, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# ── EXTRACTORES PUROS ────────────────────────────────────────────────────────

def _extract_business_model(profile: dict) -> float:
    scores = {
        'B2B_SAAS': 1.0,
        'INDUSTRIAL_MANUFACTURING': 0.933,
        'LOGISTICS_DISTRIBUTION': 0.833,
        'B2B_SERVICES': 0.733,
        'B2B_PRODUCT': 0.600,
        'MIXED': 0.400,
        'B2C': 0.166,
        'UNKNOWN': 0.0,
    }
    return scores.get(profile.get('business_model', 'UNKNOWN'), 0.0)


def _extract_scale(profile: dict) -> float:
    scores = {
        'MEDIUM_BUSINESS': 1.0,
        'SMALL_BUSINESS': 0.72,
        'LARGE_BUSINESS': 0.56,
        'EXTRA_LARGE_BUSINESS': 0.40,
        'MICRO_ENTERPRISE': 0.20,
        'UNKNOWN': 0.0,
    }
    return scores.get(profile.get('estimated_scale', 'UNKNOWN'), 0.0)


def _extract_digital(profile: dict) -> float:
    ds = profile.get('digital_signals', {})
    pts = 0
    if ds.get('has_client_portal'):     pts += 8
    if ds.get('modern_tech_stack'):     pts += 7
    if ds.get('has_e_commerce'):        pts += 5
    if ds.get('active_hiring_signals'): pts += 2
    return min(1.0, pts / 15.0)


def _extract_thesis(profile: dict) -> float:
    thesis = profile.get('investment_thesis', {})
    pts = 0
    if thesis.get('buy_and_build_potential'):         pts += 15
    # Gradual scoring: None (uncertain) gets partial credit instead of full zero.
    # This reduces score amplification when the LLM oscillates between null and true.
    # True → 15pts | None → 5pts (uncertainty penalty) | False → 0pts
    founder_led = profile.get('is_family_owned_or_founder_led')
    if founder_led is True:
        pts += 15
    elif founder_led is None:
        pts += 5   # Conservative partial credit for unconfirmed succession signal
    return min(1.0, pts / 30.0)


# ── EXTRACTORES FASE B ─────────────────────────────────────────────────────────────────────────────

def _extract_recurring_revenue(profile: dict) -> float:
    """Binario: la empresa tiene o no tiene señales de ingresos recurrentes."""
    return 1.0 if profile.get('has_recurring_revenue_signals', False) else 0.0


def _extract_industry_certs(profile: dict) -> float:
    """Binario: la empresa tiene o no tiene certificaciones industriales relevantes."""
    return 1.0 if profile.get('has_industry_certifications', False) else 0.0


def _extract_geographic_reach(profile: dict) -> float:
    """
    Escalar: mapea el Enum GeographicFootprint a un score de atractividad PE.
    Internacional > Ibérica > Nacional > Local.
    Compatible con perfiles viejos (campo ausente -> 0.0).
    """
    scores = {
        'INTERNATIONAL': 1.0,
        'IBERIAN': 0.75,
        'NATIONAL': 0.50,
        'LOCAL': 0.20,
        'UNKNOWN': 0.0,
    }
    # geographic_footprint es el campo nuevo; geographic_reach es el legado (str libre)
    footprint = profile.get('geographic_footprint', 'UNKNOWN')
    return scores.get(str(footprint).upper(), 0.0)


# ── SCORING CRITERIA CATALOG ──────────────────────────────────────────────────

SCORING_CRITERIA: Dict[str, dict] = {
    # ── PHASE A: Universal criteria (available across all profiles) ─────────────
    'w_bm': {
        'label': 'Business Model',
        'description': 'Model quality & recurring profile: B2B SaaS > Industrial > B2B Services > B2C',
        'icon': '🏗️',
        'extractor': _extract_business_model,
        'default_weight': 30,
        'group': 'Commercial',
        'phase': 'A',
    },
    'w_scale': {
        'label': 'Scale / Headcount',
        'description': 'Company size: focus on Medium (50-249 FTEs) for Lower Mid-Market Buyouts',
        'icon': '📏',
        'extractor': _extract_scale,
        'default_weight': 25,
        'group': 'Scale',
        'phase': 'A',
    },
    'w_digital': {
        'label': 'Digital Maturity',
        'description': 'Digital transformation signals: client portal, modern tech stack, e-commerce',
        'icon': '💻',
        'extractor': _extract_digital,
        'default_weight': 15,
        'group': 'Value Creation',
        'phase': 'A',
    },
    'w_thesis': {
        'label': 'M&A / Succession Potential',
        'description': 'Buy-and-Build platform potential and family business succession opportunity',
        'icon': '🤝',
        'extractor': _extract_thesis,
        'default_weight': 30,
        'group': 'Governance & M&A',
        'phase': 'A',
    },
    # ── PHASE B: Enhanced signals (extracted via updated LLM schema) ───────────
    'recurring_revenue': {
        'label': 'Recurring Revenue',
        'description': 'Recurring contracts, subscriptions, retainers, maintenance plans, or SaaS model',
        'icon': '💰',
        'extractor': _extract_recurring_revenue,
        'default_weight': 20,
        'group': 'Commercial',
        'phase': 'B',
    },
    'industry_certs': {
        'label': 'Industry Certifications',
        'description': 'ISO 9001/27001, GMP, CE mark, regulatory licenses, or sector-specific certifications',
        'icon': '🏅',
        'extractor': _extract_industry_certs,
        'default_weight': 15,
        'group': 'Defensibility',
        'phase': 'B',
    },
    'geographic_reach': {
        'label': 'Geographic Reach',
        'description': 'Expansion score: International (1.0) > Regional/Iberian (0.75) > National (0.50) > Local (0.20)',
        'icon': '🌍',
        'extractor': _extract_geographic_reach,
        'default_weight': 15,
        'group': 'Scale',
        'phase': 'B',
    },
}

THESIS_PRESETS: Dict[str, dict] = {
    'Balanced Mid-Market (Standard)': {
        'active_criteria': ['w_bm', 'w_scale', 'w_digital', 'w_thesis'],
        'weights': {'w_bm': 30, 'w_scale': 25, 'w_digital': 15, 'w_thesis': 30},
        'knockout_b2b': False,
        'knockout_min_scale': None,
        'desc': 'Balanced approach for Buyouts in industrial and B2B SME targets.',
    },
    'Aggressive Buy-and-Build (Roll-Up)': {
        'active_criteria': ['w_bm', 'w_scale', 'w_thesis'],
        'weights': {'w_bm': 25, 'w_scale': 25, 'w_thesis': 50},
        'knockout_b2b': True,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Prioritizes inorganic consolidation and succession. Discards B2C and micro-enterprises.',
    },
    'Asset-Light & Digital Transformation': {
        'active_criteria': ['w_bm', 'w_digital', 'w_scale'],
        'weights': {'w_bm': 40, 'w_digital': 40, 'w_scale': 20},
        'knockout_b2b': False,
        'knockout_min_scale': None,
        'desc': 'Focus on B2B SaaS, customer portals, and technology modernization.',
    },
    'Founder Succession / Generational Transition': {
        'active_criteria': ['w_bm', 'w_scale', 'w_thesis'],
        'weights': {'w_bm': 20, 'w_scale': 25, 'w_thesis': 55},
        'knockout_b2b': False,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Focus on family-owned and founder-led companies with succession opportunity.',
    },
    'SaaS Growth & Recurring Revenue': {
        'active_criteria': ['w_bm', 'recurring_revenue', 'w_digital', 'geographic_reach'],
        'weights': {'w_bm': 35, 'recurring_revenue': 35, 'w_digital': 20, 'geographic_reach': 10},
        'knockout_b2b': True,
        'knockout_min_scale': None,
        'desc': 'Prioritizes SaaS models and recurring revenue contracts with geographic expansion potential.',
    },
    'Industrial Defensibility & Moats': {
        'active_criteria': ['w_bm', 'w_scale', 'industry_certs', 'recurring_revenue'],
        'weights': {'w_bm': 30, 'w_scale': 25, 'industry_certs': 25, 'recurring_revenue': 20},
        'knockout_b2b': False,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Focus on industrial SMEs with regulatory barriers (ISO, CE, GMP) and recurring revenues.',
    },
}

SCALE_ORDER: List[str] = [
    'MICRO_ENTERPRISE',
    'SMALL_BUSINESS',
    'MEDIUM_BUSINESS',
    'LARGE_BUSINESS',
    'EXTRA_LARGE_BUSINESS',
    'UNKNOWN',
]


class InvestmentMandateConfig(BaseModel):
    active_criteria: List[str] = Field(
        default=['w_bm', 'w_scale', 'w_digital', 'w_thesis'],
    )
    weights: Dict[str, float] = Field(
        default={'w_bm': 30.0, 'w_scale': 25.0, 'w_digital': 15.0, 'w_thesis': 30.0},
    )
    knockout_b2b: bool = Field(default=False)
    knockout_min_scale: Optional[str] = Field(default=None)

    @model_validator(mode='after')
    def validate_criteria_have_weights(self) -> 'InvestmentMandateConfig':
        for key in self.active_criteria:
            if key not in SCORING_CRITERIA:
                raise ValueError(f'Unknown criterion: {key!r}')
            if key not in self.weights:
                self.weights[key] = SCORING_CRITERIA[key]['default_weight']
        return self
