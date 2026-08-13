from pydantic import BaseModel, Field
from typing import List, Optional

class EBITDAAdjustmentItem(BaseModel):
    category: str = Field(description="Ej. Gastos no recurrenter, Ajuste salario fundador, Indemnizaciones")
    description: str = Field(description="Detalle del ajuste hallado en la memoria/CIM")
    amount_eur: float = Field(description="Impacto monetario en euros (+ para sumas al EBITDA, - para deducciones)")
    confidence: str = Field(description="HIGH, MEDIUM, LOW según explicitud en el documento")

class EBITDABridgeAnalysis(BaseModel):
    reported_ebitda: float = Field(description="EBITDA reportado oficial")
    adjusted_ebitda: float = Field(description="EBITDA final ajustado tras add-backs")
    adjustments: List[EBITDAAdjustmentItem]
    net_adjustment_total: float