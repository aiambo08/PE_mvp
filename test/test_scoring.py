# test_scoring.py
from app.models.structured_schemas import (
    StructuredCompanyProfile, BusinessModelType, CompanyScaleCategory,
    DigitalMaturitySignals, PEInvestmentThesis
)
from app.services.scoring_service import PEScoringEngine

# 1. Crear un perfil de prueba simulado (Tier 1 ideal: SaaS B2B, Mediana empresa, Alta madurez digital)
dummy_profile = StructuredCompanyProfile(
    company_name="TechCorp Solutions",
    business_model=BusinessModelType.B2B_SAAS, # 30 pts
    core_activity="Desarrollo de software ERP industrial en la nube.",
    target_sectors=["Manufactura", "Logística"],
    estimated_scale=CompanyScaleCategory.MEDIUM_BUSINESS, # 25 pts
    geographic_reach="Internacional",
    is_family_owned_or_founder_led=True, # 15 pts
    digital_signals=DigitalMaturitySignals(
        has_client_portal=True, # 8 pts
        modern_tech_stack=True, # 7 pts
        has_e_commerce=False,
        active_hiring_signals=True # 2 pts -> Suma 17 -> Cap en 15 pts (FIX 9)
    ),
    investment_thesis=PEInvestmentThesis(
        key_strengths=["Ingresos recurrentes (ARR)", "Baja tasa de churn"],
        operational_risks=["Dependencia de cliente principal"],
        buy_and_build_potential=True, # 15 pts
        reasoning_summary="Excelente candidato para consolidación mediante buy-and-build."
    )
)

result = PEScoringEngine.calculate_score(dummy_profile)
print("Puntuación total:", result["total_score"])  # Debería dar 85.0 (Capped a 100 max)
print("Tier asignado:", result["tier"])          # Debería ser 'TIER_1_HIGH_PRIORITY'
print("Desglose:", result["score_breakdown"])
