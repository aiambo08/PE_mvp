from pydantic import BaseModel, Field
from typing import List, Optional

class EBITDAAdjustmentItem(BaseModel):
    category: str = Field(description="Ej. Gastos no recurrentes, Ajuste salario fundador, Indemnizaciones")
    description: str = Field(description="Detalle del ajuste hallado en la memoria/CIM")
    amount_eur: float = Field(description="Impacto monetario en euros (+ para sumas al EBITDA, - para deducciones)")
    confidence: str = Field(description="HIGH, MEDIUM, LOW según explicitud en el documento")

class EBITDABridgeAnalysis(BaseModel):
    reported_ebitda: float = Field(description="EBITDA reportado oficial")
    adjusted_ebitda: float = Field(description="EBITDA final ajustado tras add-backs")
    adjustments: List[EBITDAAdjustmentItem]
    net_adjustment_total: float


class FinancialScenarioResult(BaseModel):
    revenue_shock_pct: str = Field(description="Porcentaje de caída de ingresos simulada (ej. '0%', '-10%')")
    simulated_revenue_k: float = Field(description="Facturación resultante en miles de euros")
    simulated_ebitda_k: float = Field(description="EBITDA resultante en miles de euros tras impacto DOL")
    simulated_ebitda_margin_pct: float = Field(description="Margen EBITDA porcentual simulado")
    net_debt_k: float = Field(description="Deuda Financiera Neta en miles de euros")
    simulated_leverage_ratio: float = Field(
        description="Ratio DFN/EBITDA. 0.0 si la empresa se encuentra en posición de Caja Neta."
    )
    covenant_limit: float = Field(description="Límite máximo fijado por el covenant bancario")
    covenant_breached: bool = Field(description="True si el ratio de apalancamiento supera el límite")
    covenant_headroom_pct: float = Field(
        description="Margen porcentual de holgura sobre el EBITDA antes de incurrir en Default"
    )
    dscr_ratio: float = Field(
        description="Debt Service Coverage Ratio asumido para el servicio anual de deuda."
    )

class SensitivityMatrixResponse(BaseModel):
    base_revenue_k: float
    base_ebitda_k: float
    base_net_debt_k: float
    fixed_cost_ratio: float
    scenarios: List[FinancialScenarioResult]