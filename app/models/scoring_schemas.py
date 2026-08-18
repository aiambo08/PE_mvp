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
    if profile.get('is_family_owned_or_founder_led'): pts += 15
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


# ── CATÁLOGO DE CRITERIOS ────────────────────────────────────────────────────

SCORING_CRITERIA: Dict[str, dict] = {
    # ── FASE A: Criterios con datos en todos los perfiles (incluso antiguos) ─────
    'w_bm': {
        'label': 'Modelo de Negocio',
        'description': 'Calidad y recurrencia del modelo: B2B SaaS > Industrial > Servicios B2B > B2C',
        'icon': '🏗️',
        'extractor': _extract_business_model,
        'default_weight': 30,
        'group': 'Comercial',
        'phase': 'A',
    },
    'w_scale': {
        'label': 'Escala / Headcount',
        'description': 'Tamaño de la empresa: foco en Medianas (50-249 FTEs) para Buyout Mid-Market',
        'icon': '📏',
        'extractor': _extract_scale,
        'default_weight': 25,
        'group': 'Escala',
        'phase': 'A',
    },
    'w_digital': {
        'label': 'Madurez Digital',
        'description': 'Señales de transformación digital: portal de clientes, stack moderno, e-commerce',
        'icon': '💻',
        'extractor': _extract_digital,
        'default_weight': 15,
        'group': 'Creación de Valor',
        'phase': 'A',
    },
    'w_thesis': {
        'label': 'Potencial M&A / Relevo',
        'description': 'Señales de Buy-and-Build y empresa familiar con oportunidad de sucesión',
        'icon': '🤝',
        'extractor': _extract_thesis,
        'default_weight': 30,
        'group': 'Gobernanza & M&A',
        'phase': 'A',
    },
    # ── FASE B: Criterios nuevos — requieren análisis post-actualización ─────────
    'recurring_revenue': {
        'label': 'Ingresos Recurrentes',
        'description': 'Contratos recurrentes, suscripciones, cuotas mensuales, retainers o modelo SaaS',
        'icon': '💰',
        'extractor': _extract_recurring_revenue,
        'default_weight': 20,
        'group': 'Comercial',
        'phase': 'B',
    },
    'industry_certs': {
        'label': 'Certificaciones Industriales',
        'description': 'ISO 9001/27001, GMP, marcado CE, licencias regulatorias o certificaciones sectoriales',
        'icon': '🏅',
        'extractor': _extract_industry_certs,
        'default_weight': 15,
        'group': 'Defensibilidad',
        'phase': 'B',
    },
    'geographic_reach': {
        'label': 'Alcance Geográfico',
        'description': 'Puntuación de expansión: Internacional (1.0) > Ibérica (0.75) > Nacional (0.50) > Local (0.20)',
        'icon': '🌍',
        'extractor': _extract_geographic_reach,
        'default_weight': 15,
        'group': 'Escala',
        'phase': 'B',
    },
}

THESIS_PRESETS: Dict[str, dict] = {
    'Equilibrado Mid-Market (Estándar)': {
        'active_criteria': ['w_bm', 'w_scale', 'w_digital', 'w_thesis'],
        'weights': {'w_bm': 30, 'w_scale': 25, 'w_digital': 15, 'w_thesis': 30},
        'knockout_b2b': False,
        'knockout_min_scale': None,
        'desc': 'Enfoque general para Buyouts en Pymes industriales y B2B.',
    },
    'Aggressive Buy-and-Build (Roll-Up)': {
        'active_criteria': ['w_bm', 'w_scale', 'w_thesis'],
        'weights': {'w_bm': 25, 'w_scale': 25, 'w_thesis': 50},
        'knockout_b2b': True,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Prioriza consolidación inorgánica y relevo generacional. Descarta B2C y microempresas.',
    },
    'Asset-Light & Transformación Digital': {
        'active_criteria': ['w_bm', 'w_digital', 'w_scale'],
        'weights': {'w_bm': 40, 'w_digital': 40, 'w_scale': 20},
        'knockout_b2b': False,
        'knockout_min_scale': None,
        'desc': 'Foco en B2B SaaS, portales de clientes y modernización tech.',
    },
    'Relevo Generacional / Fundador': {
        'active_criteria': ['w_bm', 'w_scale', 'w_thesis'],
        'weights': {'w_bm': 20, 'w_scale': 25, 'w_thesis': 55},
        'knockout_b2b': False,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Foco en empresas familiares con oportunidad de sucesión.',
    },
    'SaaS Growth & Recurrencia': {
        'active_criteria': ['w_bm', 'recurring_revenue', 'w_digital', 'geographic_reach'],
        'weights': {'w_bm': 35, 'recurring_revenue': 35, 'w_digital': 20, 'geographic_reach': 10},
        'knockout_b2b': True,
        'knockout_min_scale': None,
        'desc': 'Prioriza modelos SaaS y contratos de ingresos recurrentes con potencial de expansión geográfica.',
    },
    'Defensibilidad Industrial': {
        'active_criteria': ['w_bm', 'w_scale', 'industry_certs', 'recurring_revenue'],
        'weights': {'w_bm': 30, 'w_scale': 25, 'industry_certs': 25, 'recurring_revenue': 20},
        'knockout_b2b': False,
        'knockout_min_scale': 'SMALL_BUSINESS',
        'desc': 'Foco en pymes industriales con barreras regulatorias (ISO, CE, GMP) e ingresos recurrentes.',
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
                raise ValueError(f'Criterio desconocido: {key!r}')
            if key not in self.weights:
                self.weights[key] = SCORING_CRITERIA[key]['default_weight']
        return self
