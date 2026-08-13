import os
from weasyprint import HTML
from app.models.structured_schemas import StructuredCompanyProfile

class ICReportGenerator:
    @staticmethod
    def generate_one_pager_pdf(
        domain: str,
        profile: dict,
        scoring: dict,
        output_path: str
    ) -> str:
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
                <h1>INVESTMENT TEASER: {profile['company_name'].upper()}</h1>
                <p style="margin:2px 0 0 0; color:#94a3b8;">Dominio: {domain} | Fecha: 2026</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <div>PE TARGET SCORE</div>
                    <div class="metric-value">{scoring['total_score']} / 100</div>
                </div>
                <div class="card">
                    <div>TIER ASIGNADO</div>
                    <div class="metric-value">{scoring['target_tier']}</div>
                </div>
                <div class="card">
                    <div>MODELO DE NEGOCIO</div>
                    <div class="metric-value" style="font-size:10pt;">{profile['business_model']}</div>
                </div>
            </div>

            <div class="card" style="margin-bottom:10px;">
                <h3>Actividad Core</h3>
                <p>{profile['core_activity']}</p>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>💡 Fortalezas Clave</h3>
                    <ul>
                        {"".join([f"<li>{s}</li>" for s in profile['investment_thesis']['key_strengths']])}
                    </ul>
                </div>
                <div class="card">
                    <h3>⚠️ Riesgos Operativos</h3>
                    <ul>
                        {"".join([f"<li>{r}</li>" for r in profile['investment_thesis']['operational_risks']])}
                    </ul>
                </div>
            </div>

            <div class="card">
                <h3>📝 Resumen para el Comité de Inversión</h3>
                <p>{profile['investment_thesis']['reasoning_summary']}</p>
            </div>
        </body>
        </html>
        """
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        HTML(string=html_template).write_pdf(output_path)
        return output_path