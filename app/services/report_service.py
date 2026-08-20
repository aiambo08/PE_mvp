import os
import concurrent.futures
from app.models.structured_schemas import StructuredCompanyProfile


class ICReportGenerator:
    @staticmethod
    def generate_one_pager_pdf(
        domain: str,
        profile: dict,
        scoring: dict,
        output_path: str,
        contact_email: str | None = None,
        social_links: list[str] | None = None,
    ) -> str:
        company_name = profile.get("company_name", "N/A")
        total_score = scoring.get("total_score", 0)
        tier_val = scoring.get("tier", scoring.get("target_tier", "N/A"))
        business_model = profile.get("business_model", "N/A").replace("_", " ").title()
        core_activity = profile.get("core_activity", "Sin descripcion disponible.")
        thesis = profile.get("investment_thesis", {})
        key_strengths = thesis.get("key_strengths", [])
        operational_risks = thesis.get("operational_risks", [])
        reasoning = thesis.get("reasoning_summary", "Sin resumen ejecutivo.")

        s_rows = "".join(["<li>" + x + "</li>" for x in key_strengths]) or "<li>N/A</li>"
        r_rows = "".join(["<li>" + x + "</li>" for x in operational_risks]) or "<li>N/A</li>"

        # Desglose generico -- compatible con cualquier combinacion de criterios activos
        breakdown = scoring.get("score_breakdown", {})
        ko_reason = scoring.get("knockout_reason")
        if ko_reason:
            b_rows = "<li>Descartado (Knockout): " + str(ko_reason) + "</li>"
        elif breakdown:
            b_rows = "".join([
                "<li>" + str(k) + ": " + str(round(v, 1)) + " pts</li>"
                for k, v in breakdown.items()
            ])
        else:
            b_rows = "<li>Sin desglose disponible</li>"

        # Canales de contacto y outreach
        contact_parts = []
        if contact_email:
            contact_parts.append(f"<strong>Email:</strong> {contact_email}")
        if social_links:
            social_tags = " ".join([f"<span style='background:#e2e8f0;padding:2px 6px;border-radius:3px;margin-right:4px;'>{link}</span>" for link in social_links])
            contact_parts.append(f"<strong>Redes:</strong> {social_tags}")
        contact_row = f"<div class=card style=margin-bottom:10px><h3>Contacto & Outreach</h3><p>{' | '.join(contact_parts)}</p></div>" if contact_parts else ""

        # Build HTML via list join to avoid f-string brace conflicts with CSS
        css = (
            "body{font-family:Helvetica;font-size:8.5pt;color:#0f172a;}"
            ".hdr{background:#0f172a;color:white;padding:12px;margin-bottom:12px;}"
            ".hdr h1{margin:0;font-size:14pt;}"
            ".grid{display:flex;gap:10px;margin-bottom:10px;}"
            ".card{border:1px solid #cbd5e1;padding:8px;flex:1;border-radius:4px;}"
            ".mv{font-size:14pt;font-weight:bold;color:#2563eb;}"
            "ul{margin:0;padding-left:12px;}"
        )
        rows = [
            "<!DOCTYPE html><html><head><meta charset=utf-8><style>" + css + "</style></head><body>",
            "<div class=hdr><h1>INVESTMENT TEASER: " + company_name.upper() + "</h1>",
            "<p>Dominio: " + domain + " | Fecha: 2026</p></div>",
            "<div class=grid>",
            "<div class=card><p>PE TARGET SCORE</p><p class=mv>" + str(total_score) + " / 100</p></div>",
            "<div class=card><p>TIER ASIGNADO</p><p class=mv>" + str(tier_val) + "</p></div>",
            "<div class=card><p>MODELO</p><p class=mv style=font-size:10pt>" + business_model + "</p></div>",
            "</div>",
            "<div class=card style=margin-bottom:10px><h3>Actividad Core</h3><p>" + core_activity + "</p></div>",
            contact_row,
            "<div class=grid>",
            "<div class=card><h3>Fortalezas Clave</h3><ul>" + s_rows + "</ul></div>",
            "<div class=card><h3>Riesgos Operativos</h3><ul>" + r_rows + "</ul></div>",
            "</div>",
            "<div class=card><h3>Desglose PE Score (Criterios Activos)</h3><ul>" + b_rows + "</ul></div>",
            "<div class=card><h3>Resumen IC</h3><p>" + reasoning + "</p></div>",
            "</body></html>",
        ]
        html_template = "".join(rows)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        def _playwright_render():
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.set_content(html_template)
                page.pdf(
                    path=output_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                )
                browser.close()

        try:
            from weasyprint import HTML
            HTML(string=html_template).write_pdf(output_path)
        except Exception:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(_playwright_render).result()

        return output_path
