from typing import Any, Dict, List
from app.models.financial_schemas import SensitivityMatrixResponse


class FinancialStressEngine:
    """
    Motor institucional de estrés financiero y covenants LBO para Comités de Inversión.
    Incorpora CFADS (Cash Flow Available for Debt Service) y Operating Leverage (DOL).
    """

    @staticmethod
    def run_sensitivity_matrix(
        revenue: float,
        ebitda: float,
        net_debt: float,
        max_covenant_ratio: float = 3.0,
        fixed_cost_ratio: float = 0.60,
        interest_rate_pct: float = 0.055,       # Euribor + Margen (ej. 5.5%)
        debt_amortization_years: int = 7,       # Amortización lineal 7 años
        maintenance_capex_pct: float = 0.03,    # 3% sobre ventas para Capex de reposición
        tax_rate: float = 0.25,                 # Tipo impositivo nominal 25%
        annual_debt_service: float | None = None,
    ) -> Dict[str, Any]:
        """
        Modela la solvencia LBO y la rotura de covenants ante caídas de demanda (-5% a -20%).
        
        Mecánica Institucional:
        1. Descomposición de Costes Fijos vs. Variables según estructura operativa.
        2. Cálculo de CFADS = EBITDA - Capex Mantenimiento - Impuestos Estimados.
        3. Servicio de Deuda Anual = Intereses (DFN * i) + Principal (DFN / Plazo).
        4. DSCR Institucional = CFADS / Servicio Anual de Deuda.
        """
        if revenue <= 0 or ebitda <= 0:
            raise ValueError("Los ingresos y el EBITDA base deben ser valores estrictamente positivos.")

        total_costs = revenue - ebitda
        variable_costs = total_costs * (1.0 - fixed_cost_ratio)
        variable_cost_rate = variable_costs / revenue

        # Servicio de Deuda Estructurado (si no se proporciona valor explícito)
        if annual_debt_service is not None and annual_debt_service > 0:
            debt_service = annual_debt_service
        else:
            annual_interest = net_debt * interest_rate_pct if net_debt > 0 else 0.0
            annual_principal = (net_debt / max(1, debt_amortization_years)) if net_debt > 0 else 0.0
            debt_service = max(1.0, annual_interest + annual_principal)

        scenarios: List[Dict[str, Any]] = []

        for shock in [0.0, -0.05, -0.10, -0.15, -0.20]:
            sim_revenue = revenue * (1.0 + shock)
            revenue_drop = revenue - sim_revenue
            
            # Absorción de costes variables y caída neta de EBITDA
            variable_savings = revenue_drop * variable_cost_rate
            ebitda_drop = revenue_drop - variable_savings
            sim_ebitda = max(1.0, ebitda - ebitda_drop)

            # Cálculo de CFADS (Caja disponible para pagar deuda)
            sim_capex = sim_revenue * maintenance_capex_pct
            sim_ebit = max(0.0, sim_ebitda - sim_capex)  # Proxy de EBIT tras amortizaciones
            sim_tax = sim_ebit * tax_rate
            sim_cfads = max(0.0, sim_ebitda - sim_capex - sim_tax)

            # Ratio de Apalancamiento DFN / EBITDA
            if net_debt > 0:
                sim_leverage = round(net_debt / sim_ebitda, 2)
                covenant_breached = sim_leverage > max_covenant_ratio
                required_ebitda = net_debt / max_covenant_ratio
                headroom_pct = round(((sim_ebitda - required_ebitda) / required_ebitda) * 100, 1)
            else:
                sim_leverage = 0.0
                covenant_breached = False
                headroom_pct = 100.0

            # DSCR sobre CFADS (Estándar de Banca de Inversión y PE)
            sim_dscr = round(sim_cfads / debt_service, 2)

            scenarios.append({
                "revenue_shock_pct": f"{int(shock * 100)}%",
                "simulated_revenue_k": round(sim_revenue / 1_000, 2),
                "simulated_ebitda_k": round(sim_ebitda / 1_000, 2),
                "simulated_cfads_k": round(sim_cfads / 1_000, 2),
                "simulated_ebitda_margin_pct": round((sim_ebitda / sim_revenue) * 100, 1),
                "net_debt_k": round(net_debt / 1_000, 2),
                "simulated_leverage_ratio": sim_leverage,
                "covenant_limit": max_covenant_ratio,
                "covenant_breached": covenant_breached,
                "covenant_headroom_pct": headroom_pct,
                "dscr_ratio": sim_dscr,
            })

        return {
            "base_revenue_k": round(revenue / 1_000, 2),
            "base_ebitda_k": round(ebitda / 1_000, 2),
            "base_net_debt_k": round(net_debt / 1_000, 2),
            "annual_debt_service_k": round(debt_service / 1_000, 2),
            "fixed_cost_ratio": fixed_cost_ratio,
            "scenarios": scenarios,
        }
