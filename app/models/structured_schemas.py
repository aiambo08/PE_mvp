from enum import Enum
from typing import Annotated, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BusinessModelType(str, Enum):
    B2B_SERVICES = "B2B_SERVICES"
    B2B_PRODUCT = "B2B_PRODUCT"
    B2B_SAAS = "B2B_SAAS"
    INDUSTRIAL_MANUFACTURING = "INDUSTRIAL_MANUFACTURING"
    LOGISTICS_DISTRIBUTION = "LOGISTICS_DISTRIBUTION"
    B2C = "B2C"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class CompanyScaleCategory(str, Enum):
    MICRO_ENTERPRISE = "MICRO_ENTERPRISE"   # < 10 empleados
    SMALL_BUSINESS = "SMALL_BUSINESS"       # 10–49
    MEDIUM_BUSINESS = "MEDIUM_BUSINESS"     # 50–249
    LARGE_BUSINESS = "LARGE_BUSINESS"       # 250–999
    EXTRA_LARGE_BUSINESS = "EXTRA_LARGE_BUSINESS"
    UNKNOWN = "UNKNOWN"


class DigitalMaturitySignals(BaseModel):
    # use_enum_values: serializa Enums como strings en el JSON schema enviado al LLM
    model_config = ConfigDict(use_enum_values=True)

    has_client_portal: bool = Field(default=False, description="¿Tiene portal de clientes o intranet?")
    has_e_commerce: bool = Field(default=False, description="¿Vende directamente online?")
    modern_tech_stack: bool = Field(default=False, description="¿Menciona APIs, nube o software propio?")
    active_hiring_signals: bool = Field(default=False, description="¿Menciona expansión de equipo?")


class PEInvestmentThesis(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    # FIX Pydantic v2: max_length en Field sobre List limita el nº de elementos correctamente
    key_strengths: Annotated[List[str], Field(min_length=1, max_length=5)] = Field(
        description="Puntos fuertes para un fondo (ingresos recurrentes, escalabilidad, etc.)"
    )
    operational_risks: Annotated[List[str], Field(min_length=1, max_length=5)] = Field(
        description="Riesgos e ineficiencias clave"
    )
    buy_and_build_potential: bool = Field(description="¿Permite consolidación inorgánica?")
    reasoning_summary: str = Field(description="Resumen ejecutivo para el Investment Committee")


class StructuredCompanyProfile(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    company_name: str = Field(description="Nombre comercial de la empresa")
    business_model: BusinessModelType = Field(description="Modelo de negocio principal")
    core_activity: str = Field(description="Descripción concisa de la actividad principal (1-2 frases).")
    target_sectors: List[str] = Field(description="Sectores o industrias a los que sirve la empresa")
    estimated_scale: CompanyScaleCategory = Field(
        default=CompanyScaleCategory.UNKNOWN, description="Escala estimada de la empresa"
    )
    geographic_reach: str = Field(description="Alcance: Nacional, Regional, Internacional")
    is_family_owned_or_founder_led: Optional[bool] = Field(
        default=None, description="¿Es pyme familiar o gestionada por el fundador?"
    )
    digital_signals: DigitalMaturitySignals = Field(description="Señales de madurez digital")
    investment_thesis: PEInvestmentThesis = Field(description="Tesis de inversión para el fondo")

    @field_validator("target_sectors")
    @classmethod
    def clean_sectors(cls, v: List[str]) -> List[str]:
        return [sector.strip().title() for sector in v if sector.strip()]
