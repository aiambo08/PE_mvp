import os
import concurrent.futures
from app.models.structured_schemas import StructuredCompanyProfile

class ICReportGenerator:
    @staticmethod
    def generate_one_pager_pdf(
        domain: str,
        profile: dict,
        scoring: dict,
        output_path: str
    ) -> str:
        company_name = profile.get("company_name", "N/A")
        total_score = scoring.get("total_score", 0)
        tier_val = scoring.get("tier", scoring.get("target_tier", "N/A"))
        business_model = profile.get("business_model", "N/A").replace("_", " ").title()
        core_activity = profile.get("core_activity", "Sin descripción disponible.")
        
        investment_thesis = profile.get("investment_thesis", {})
        key_strengths = investment_thesis.get("key_strengths", [])
        operational_risks = investment_thesis.get("operational_risks", [])
        reasoning_summary = investment_thesis.get("reasoning_summary", "Sin resumen ejecutivo.")

        strengths_html = "".join([f"<li>{s}</li>" for s in key_strengths]) if key_strengths else "<li>N/A</li>"
        risks_html = "".join([f"<li>{r}</li>" for r in operational_risks]) if operational_risks else "<li>N/A</li>"

        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                @page {{ size: A4; margin: 12mm; }}
                body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 8.5pt; color: #0f172a; }}
                .header {{ background-color: #0f172a; color: white; padding: 12px; margin-bottom: 12px; }}
                .header h1 {{ margin: 0; font-size: 14pt; }}
                .badge {{ background-color: #2563eb; padding: 3px 6px; font-weight: bold; border-radius: 3px; }}
                .grid {{ display: flex; gap: 10px; margin-bottom: 10px; }}
                .card {{ border: 1px solid #cbd5e1; padding: 8px; flex: 1; border-radius: 4px; }}
                .metric-value {{ font-size: 14pt; font-weight: bold; color: #2563eb; }}
                ul {{ margin: 0; padding-left: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>INVESTMENT TEASER: {company_name.upper()}</h1>
                <p style="margin:2px 0 0 0; color:#94a3b8;">Dominio: {domain} | Fecha: 2026</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <div>PE TARGET SCORE</div>
                    <div class="metric-value">{total_score} / 100</div>
                </div>
                <div class="card">
                    <div>TIER ASIGNADO</div>
                    <div class="metric-value">{tier_val}</div>
                </div>
                <div class="card">
                    <div>MODELO DE NEGOCIO</div>
                    <div class="metric-value" style="font-size:10pt;">{business_model}</div>
                </div>
            </div>

            <div class="card" style="margin-bottom:10px;">
                <h3>Actividad Core</h3>
                <p>{core_activity}</p>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>💡 Fortalezas Clave</h3>
                    <ul>
                        {strengths_html}
                    </ul>
                </div>
                <div class="card">
                    <h3>⚠️ Riesgos Operativos</h3>
                    <ul>
                        {risks_html}
                    </ul>
                </div>
            </div>

            <div class="card">
                <h3>📝 Resumen para el Comité de Inversión</h3>
                <p>{reasoning_summary}</p>
            </div>
        </body>
        </html>
        """
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        def _playwright_render():
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_content(html_template)
                page.pdf(
                    path=output_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"}
                )
                browser.close()

        # Intentar primero WeasyPrint; si falla por falta de DLLs de GTK3/GObject en Windows, usar Playwright en un worker thread independiente
        try:
            from weasyprint import HTML
            HTML(string=html_template).write_pdf(output_path)
        except Exception:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_playwright_render)
                future.result()

        return output_path
