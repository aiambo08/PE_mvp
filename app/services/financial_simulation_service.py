from typing import Any, Dict, List

from app.models.financial_schemas import FinancialScenarioResult, SensitivityMatrixResponse

class FinancialStressEngine:
    """Motor institucional de sensibilidad financiera para Comités de Inversión."""
    @staticmethod
    def run_sensitivity_matrix(
        revenue: float,
        ebitda: float,
        net_debt: float,
        max_covenant_ratio: float = 3.0,
        fixed_cost_ratio: float = 0.60,
        annual_debt_service: float | None = None,
    ) -> Dict[str, Any]:
        """
        Calcula la matriz de estrés ante shocks de demanda (-5% a -20%).
        
        Mecánica de Apalancamiento Operativo (DOL):
        - Costes Totales = Revenue - EBITDA
        - Costes Fijos = Costes Totales * fixed_cost_ratio
        - Costes Variables = Costes Totales * (1 - fixed_cost_ratio)
        Ante una caída de Ingresos (ΔR), los Costes Variables caen proporcionalmente,
        pero los Costes Fijos permanecen invariables.
        Por tanto: ΔEBITDA = ΔR - ΔCostesVariables = ΔR * (1 - (CostesVariables / Revenue))
        """
        if revenue <= 0 or ebitda <= 0:
            raise ValueError("Los ingresos y el EBITDA base deben ser valores positivos estrictos.")
        total_costs = revenue - ebitda
        variable_costs = total_costs * (1.0 - fixed_cost_ratio)
        variable_cost_rate = variable_costs / revenue
        # Si no se define el servicio de deuda anual, se estima un 15% del principal de la DFN
        estimated_debt_service = annual_debt_service if annual_debt_service is not None else max(1.0, net_debt * 0.15)
        scenarios: List[Dict[str, Any]] = []
        for shock in [0.0, -0.05, -0.10, -0.15, -0.20]:
            sim_revenue = revenue * (1.0 + shock)
            revenue_drop = revenue - sim_revenue
            # Reducción de costes variables que la empresa logra absorber
            variable_cost_savings = revenue_drop * variable_cost_rate
            
            # Caída neta de EBITDA (los costes fijos no se reducen en el corto plazo)
            ebitda_drop = revenue_drop - variable_cost_savings
            sim_ebitda = max(1.0, ebitda - ebitda_drop)
            # Ratio de Apalancamiento DFN / EBITDA
            if net_debt > 0:
                sim_ratio = round(net_debt / sim_ebitda, 2)
                covenant_breached = sim_ratio > max_covenant_ratio
                
                # EBITDA mínimo requerido para cumplir covenant
                required_ebitda = net_debt / max_covenant_ratio
                headroom_pct = round(((sim_ebitda - required_ebitda) / required_ebitda) * 100, 1)
            else:
                sim_ratio = 0.0  # Posición neta de caja
                covenant_breached = False
                headroom_pct = 100.0
            # DSCR = EBITDA / Servicio Anual de Deuda (Principal + Intereses)
            sim_dscr = round(sim_ebitda / estimated_debt_service, 2)
            scenarios.append({
                "revenue_shock_pct": f"{int(shock * 100)}%",
                "simulated_revenue_k": round(sim_revenue / 1_000, 2),
                "simulated_ebitda_k": round(sim_ebitda / 1_000, 2),
                "simulated_ebitda_margin_pct": round((sim_ebitda / sim_revenue) * 100, 1),
                "net_debt_k": round(net_debt / 1_000, 2),
                "simulated_leverage_ratio": sim_ratio,
                "covenant_limit": max_covenant_ratio,
                "covenant_breached": covenant_breached,
                "covenant_headroom_pct": headroom_pct,
                "dscr_ratio": sim_dscr,
            })
        return {
            "base_revenue_k": round(revenue / 1_000, 2),
            "base_ebitda_k": round(ebitda / 1_000, 2),
            "base_net_debt_k": round(net_debt / 1_000, 2),
            "fixed_cost_ratio": fixed_cost_ratio,
            "scenarios": scenarios,
        }