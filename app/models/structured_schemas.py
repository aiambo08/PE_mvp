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
    MICRO_ENTERPRISE = "MICRO_ENTERPRISE"   # < 10 employees
    SMALL_BUSINESS = "SMALL_BUSINESS"       # 10–49
    MEDIUM_BUSINESS = "MEDIUM_BUSINESS"     # 50–249
    LARGE_BUSINESS = "LARGE_BUSINESS"       # 250–999
    EXTRA_LARGE_BUSINESS = "EXTRA_LARGE_BUSINESS"
    UNKNOWN = "UNKNOWN"


class GeographicFootprint(str, Enum):
    """Structured geographic reach of the target company."""
    LOCAL = "LOCAL"               # City / Province only
    NATIONAL = "NATIONAL"         # Entire Country (Spain / Domestic)
    IBERIAN = "IBERIAN"           # Regional / Spain + Portugal
    INTERNATIONAL = "INTERNATIONAL"  # International presence
    UNKNOWN = "UNKNOWN"


class DigitalMaturitySignals(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    has_client_portal: bool = Field(default=False, description="Does the company have a client portal or intranet?")
    has_e_commerce: bool = Field(default=False, description="Does the company sell directly online / e-commerce?")
    modern_tech_stack: bool = Field(default=False, description="Mentions APIs, cloud services, or proprietary software?")
    active_hiring_signals: bool = Field(default=False, description="Mentions team expansion or open job positions?")


class PEInvestmentThesis(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    key_strengths: Annotated[List[str], Field(min_length=1, max_length=5)] = Field(
        description="Key strengths for a Private Equity fund (recurring revenue, defensibility, scalability, etc.)"
    )
    operational_risks: Annotated[List[str], Field(min_length=1, max_length=5)] = Field(
        description="Key operational risks and potential inefficiencies"
    )
    buy_and_build_potential: bool = Field(description="Enables inorganic consolidation (add-on / roll-up platform)?")
    reasoning_summary: str = Field(description="Executive summary for the Investment Committee")


class StructuredCompanyProfile(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    company_name: str = Field(description="Commercial name of the company")
    business_model: BusinessModelType = Field(description="Primary business model")
    core_activity: str = Field(description="Concise description of the core business activity (1-2 sentences).")
    target_sectors: List[str] = Field(description="Target industries or sectors served by the company")
    estimated_scale: CompanyScaleCategory = Field(
        default=CompanyScaleCategory.UNKNOWN, description="Estimated scale/headcount of the company"
    )
    geographic_reach: str = Field(default="", description="Free-text geographic reach (legacy). See geographic_footprint.")
    is_family_owned_or_founder_led: Optional[bool] = Field(
        default=None, description="Is the company family-owned or founder-led (succession opportunity)?"
    )
    digital_signals: DigitalMaturitySignals = Field(description="Digital maturity and technology adoption signals")
    investment_thesis: PEInvestmentThesis = Field(description="Private equity investment thesis")

    geographic_footprint: GeographicFootprint = Field(
        default=GeographicFootprint.UNKNOWN,
        description=(
            "Actual geographic footprint of the company. "
            "LOCAL=city/province only. NATIONAL=country-wide. "
            "IBERIAN=Spain+Portugal/regional. INTERNATIONAL=presence outside home region."
        ),
    )
    has_recurring_revenue_signals: Optional[bool] = Field(
        default=False,
        description=(
            "Does the company show signals of recurring revenue, subscriptions, monthly fees, "
            "retainers, or SaaS business models? Signals: 'monthly fee', 'annual contract', 'subscription', 'maintenance plan'."
        ),
    )
    has_industry_certifications: Optional[bool] = Field(
        default=False,
        description=(
            "Mentions quality or industry certifications? ISO 9001, ISO 27001, GMP, "
            "CE mark, regulatory licenses, sustainability certifications or similar."
        ),
    )

    @field_validator("has_recurring_revenue_signals", "has_industry_certifications", mode="before")
    @classmethod
    def coerce_none_booleans(cls, v: bool | None) -> bool:
        """LLMs sometimes return null for boolean fields when uncertain. Coerce to False."""
        return bool(v) if v is not None else False

    @field_validator("target_sectors")
    @classmethod
    def clean_sectors(cls, v: List[str]) -> List[str]:
        return [sector.strip().title() for sector in v if sector.strip()]
