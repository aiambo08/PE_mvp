class FinancialStressEngine:
    @staticmethod
    def run_sensitivity_matrix(
        revenue: float,
        ebitda: float,
        net_debt: float,
        max_convenant_ratio: float= 3.0) -> dict:
        """
        Simula escenarios de caídas de ingresos (5%, 10%, 15%, 20%) asumiendo un apalancamineto operativo fijo y calcula el margen de ruptura de convenants
        """
        scenarios = []
        fixed_cost_ratio = 0.60 # estructura de costes fijos asumido (60%)

        for shock in [0.0, -0.05, -0.10, -0.15, -0.20]:
            sim_revenue = revenue *(1+shock)
            # impacto amplificado en EBITDA por apalancamiento operativo
            revenue_drop_amount = revenue - sim_revenue
            ebitda_drop = revenue_drop_amount * (1 - fixed_cost_ratio)
            sim_ebitda = max(1.0, ebitda - ebitda_drop)

            sim_ratio = net_debt / sim_ebitda
            covenant_breached = sim_ratio > max_convenant_ratio

            scenarios.append({
                "revenue_shock_pct": f"{int(shock * 100)}%",
                "simulated_ebitda_k": round(sim_ebitda / 1000, 2),
                "simulated_leverage_ratio": round(sim_ratio, 2),
                "covenant_breached": covenant_breached
            })
        
        return {"scenarios": scenarios}
            