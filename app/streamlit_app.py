import sys
import asyncio
from pathlib import Path

# Configurar ProactorEventLoop en Windows antes de que Streamlit cree subprocesos de Playwright
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Añadir la raíz del proyecto a sys.path para importar el módulo 'app' sin errores
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
import json, os
from typing import Dict, Any, List

from app.ui.api_client import APIClient
from app.services.report_service import ICReportGenerator
from app.ui.benchmarking_view import render_benchmarking_matrix
from app.models.scoring_schemas import (
    SCORING_CRITERIA, THESIS_PRESETS, InvestmentMandateConfig
)
from app.services.scoring_service import DynamicPEScoringEngine

# ── 1. CONFIGURACIÓN DE PÁGINA ──────────────────────────────────────────────
st.set_page_config(
    page_title="PE Deal Cockpit | M&A Sourcing & Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── 2. ESTILOS TERMINAL NOIR (INSTITUTIONAL PE DESIGN) ──────────────────────
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap');

    /* Variables de Color Terminal Noir */
    :root {
        --color-bg: #07090E;
        --color-surface: #0E131F;
        --color-surface-hover: #161D2F;
        --color-border: #1E293B;
        --color-accent: #0EA5E9;
        --color-accent-hover: #38BDF8;
        --color-tier-1: #10B981;
        --color-tier-2: #F59E0B;
        --color-tier-3: #EF4444;
        --color-text-main: #F8FAFC;
        --color-text-muted: #94A3B8;
    }

    /* Forzar fondo global y texto */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        font-family: 'Inter', -apple-system, sans-serif !important;
        background-color: var(--color-bg) !important;
        color: var(--color-text-main) !important;
    }

    /* Sidebar Forzada en Modo Oscuro */
    section[data-testid="stSidebar"] {
        background-color: var(--color-surface) !important;
        border-right: 1px solid var(--color-border) !important;
    }
    section[data-testid="stSidebar"] * {
        color: var(--color-text-main);
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] label {
        color: var(--color-text-main) !important;
    }

    /* Tipografía de Encabezados */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.03em !important;
        color: var(--color-text-main) !important;
    }

    /* Inputs, Selects y Elementos de Formulario */
    input, textarea, select, div[data-baseweb="select"] > div {
        background-color: #0E131F !important;
        color: #F8FAFC !important;
        border-color: var(--color-border) !important;
    }

    /* Etiquetas de Inputs */
    label, div[data-testid="stWidgetLabel"] p {
        color: #CBD5E1 !important;
        font-weight: 500 !important;
    }

    /* Tarjetas de Métricas de Alta Densidad */
    div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1.7rem !important;
        font-weight: 700 !important;
        color: var(--color-accent) !important;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600 !important;
        color: var(--color-text-muted) !important;
    }

    /* Contenedores con Borde y Sombra Elevada */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 8px !important;
        border: 1px solid var(--color-border) !important;
        background: linear-gradient(180deg, rgba(14, 19, 31, 0.95) 0%, rgba(10, 14, 23, 0.98) 100%) !important;
        padding: 14px !important;
        box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.4) !important;
    }

    /* Botones de Acción M&A */
    .stButton > button {
        border-radius: 6px !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 600 !important;
        border: 1px solid rgba(14, 165, 233, 0.4) !important;
        background: linear-gradient(180deg, #0284C7 0%, #0369A1 100%) !important;
        color: #FFFFFF !important;
        transition: all 0.15s ease-in-out !important;
    }

    .stButton > button:hover {
        border-color: var(--color-accent-hover) !important;
        box-shadow: 0 0 12px rgba(14, 165, 233, 0.35) !important;
        transform: translateY(-1px);
    }

    /* Tabs Institucionales */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid var(--color-border);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.88rem;
        font-weight: 600;
        padding: 8px 16px;
        border-radius: 6px 6px 0 0;
        color: var(--color-text-muted) !important;
    }

    .stTabs [aria-selected="true"] {
        color: var(--color-accent) !important;
        border-bottom: 2px solid var(--color-accent) !important;
        background-color: rgba(14, 165, 233, 0.08) !important;
    }

    /* Área de Chat de Due Diligence */
    .stChatMessage {
        border-radius: 8px !important;
        border: 1px solid var(--color-border) !important;
        background-color: rgba(14, 19, 31, 0.7) !important;
    }

    /* Badges de Citas y Fuentes */
    .citation-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        background-color: rgba(14, 165, 233, 0.15);
        color: #38BDF8;
        padding: 2px 6px;
        border-radius: 4px;
        border: 1px solid rgba(14, 165, 233, 0.3);
    }

    /* Expander styling */
    div[data-testid="stExpander"] {
        border: 1px solid var(--color-border) !important;
        border-radius: 8px !important;
        background-color: rgba(14, 19, 31, 0.6) !important;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── 3. CLIENTE DE API Y ESTADO DE SESIÓN ─────────────────────────────────────
api_client = APIClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ── 4. FUNCIÓN DE SCORING DINÁMICA (thin wrapper sobre DynamicPEScoringEngine) ─
def recalculate_dynamic_score(profile: Dict[str, Any], mandate: InvestmentMandateConfig) -> Dict[str, Any]:
    """Recalcula el score PE usando el mandato de inversión activo en la sesión."""
    return DynamicPEScoringEngine.calculate_from_mandate(profile, mandate)

def format_tier_badge(tier_raw: str) -> str:
    if not tier_raw or tier_raw == "N/A":
        return "N/A"
    mapping = {
        "TIER_1_HIGH_PRIORITY": "🟢 Tier 1 (High Priority)",
        "TIER_2_QUALIFIED": "🟡 Tier 2 (Qualified)",
        "TIER_3_DISCARD": "🔴 Tier 3 (Discard)",
    }
    return mapping.get(tier_raw, tier_raw.replace("_", " ").title())

def format_business_model(bm_raw: str) -> str:
    if not bm_raw or bm_raw == "N/A":
        return "N/A"
    return bm_raw.replace("_", " ").title()

def format_estimated_scale(scale_raw: str) -> str:
    if not scale_raw or scale_raw == "N/A":
        return "N/A"
    mapping = {
        "MICRO_ENTERPRISE": "Microenterprise (<10)",
        "SMALL_BUSINESS": "Small Business (10-49)",
        "MEDIUM_BUSINESS": "Medium Business (50-249)",
        "LARGE_BUSINESS": "Large Business (250+)",
        "UNKNOWN": "Unidentified",
    }
    return mapping.get(scale_raw, scale_raw.replace("_", " ").title())

# ── 5. SIDEBAR: THESIS CONFIGURATION DOCK ────────────────────────────────────
with st.sidebar:
    st.markdown("## 💼 PE Deal Cockpit")
    st.caption("Investment Committee Decision Terminal")
    st.markdown("---")

    # API Status
    api_status = api_client.check_health()
    if api_status:
        st.success("🟢 Backend API Connected")
    else:
        st.error("🔴 Backend API Disconnected")

    st.markdown("### ⚙️ Investment Thesis & Scoring")

    # ── Preset Selector ───────────────────────────────────────────────────────
    preset_names = list(THESIS_PRESETS.keys())
    selected_preset_name = st.selectbox("Investment Preset:", options=preset_names, index=0)
    preset_data = THESIS_PRESETS[selected_preset_name]
    st.caption(f"_{preset_data['desc']}_")

    # Detect preset change to reset session state
    if st.session_state.get("_last_preset") != selected_preset_name:
        st.session_state["_last_preset"] = selected_preset_name
        st.session_state["_active_criteria"] = list(preset_data["active_criteria"])
        st.session_state["_weights"] = dict(preset_data["weights"])
        st.session_state["_knockout_b2b"] = preset_data["knockout_b2b"]
        st.session_state["_knockout_min_scale"] = preset_data["knockout_min_scale"]

    # Ensure state exists (first render)
    if "_active_criteria" not in st.session_state:
        st.session_state["_active_criteria"] = list(preset_data["active_criteria"])
        st.session_state["_weights"] = dict(preset_data["weights"])
        st.session_state["_knockout_b2b"] = preset_data["knockout_b2b"]
        st.session_state["_knockout_min_scale"] = preset_data["knockout_min_scale"]

    with st.expander("🛠️ Customize Investment Mandate", expanded=False):

        # ── Section 1: Deal-Breakers (Knockout Filters) ──────────────────────
        st.markdown("**🚫 Deal-Breakers (Knockout Filters)**")
        knockout_b2b = st.checkbox(
            "Mandatory B2B (discards B2C and unknown models)",
            key="_knockout_b2b"
        )

        scale_options = {
            "No minimum scale": None,
            "Minimum: Small Business (10-49 FTEs)": "SMALL_BUSINESS",
            "Minimum: Medium Business (50-249 FTEs)": "MEDIUM_BUSINESS",
        }
        current_min_scale = st.session_state.get("_knockout_min_scale", preset_data["knockout_min_scale"])
        # Map stored value back to label for selectbox default
        default_scale_label = next(
            (lbl for lbl, val in scale_options.items() if val == current_min_scale),
            "No minimum scale"
        )
        selected_scale_label = st.selectbox(
            "Minimum scale required:",
            options=list(scale_options.keys()),
            index=list(scale_options.keys()).index(default_scale_label)
        )
        knockout_min_scale = scale_options[selected_scale_label]

        st.markdown("---")

        # ── Section 2: Active Criteria (Multiselect) ─────────────────────────
        st.markdown("**📐 Active Scoring Criteria**")
        all_criteria_keys = list(SCORING_CRITERIA.keys())
        criteria_labels = {k: f"{SCORING_CRITERIA[k]['icon']} {SCORING_CRITERIA[k]['label']}" for k in all_criteria_keys}

        selected_labels = st.multiselect(
            "Dimensions to evaluate:",
            options=[criteria_labels[k] for k in all_criteria_keys],
            default=[criteria_labels[k] for k in st.session_state["_active_criteria"] if k in criteria_labels],
            help="Select evaluation dimensions. Weights are automatically normalized to 100%."
        )
        # Reverse-map labels back to keys
        label_to_key = {v: k for k, v in criteria_labels.items()}
        active_criteria = [label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key]

        if not active_criteria:
            st.warning("⚠️ Select at least one criterion to calculate scoring.")
            active_criteria = list(preset_data["active_criteria"])  # fallback


        st.markdown("---")

        # ── Section 3: Dynamic Sliders (active criteria only) ────────────────
        st.markdown("**⚖️ Weights (%)**")
        raw_weights: Dict[str, float] = {}
        for key in active_criteria:
            crit = SCORING_CRITERIA[key]
            default_w = st.session_state["_weights"].get(key, crit["default_weight"])
            raw_weights[key] = st.slider(
                f"{crit['icon']} {crit['label']} (%)",
                min_value=0,
                max_value=80,
                value=int(default_w),
                step=5,
                help=crit["description"]
            )

        total_w = sum(raw_weights.values())
        if total_w == 0:
            st.warning("⚠️ Weights cannot all be 0.")
            total_w = 1
        if total_w != 100:
            st.warning(f"⚠️ Sum: **{total_w}%** → Normalized to 100% automatically")
        else:
            st.success("Weights at 100% ✅")

        # Persist weights state
        st.session_state["_weights"] = raw_weights

    # ── Construct Active Mandate ──────────────────────────────────────────────
    active_mandate = InvestmentMandateConfig(
        active_criteria=active_criteria,
        weights=raw_weights,
        knockout_b2b=knockout_b2b,
        knockout_min_scale=knockout_min_scale,
    )

    st.markdown("---")
    st.markdown("### 🎯 Quick Filters")
    target_domain_filter = st.text_input("Filter Target by Domain:", placeholder="e.g. scale.com")
    min_score_filter = st.slider("Minimum Score (Cut-off):", 0, 90, 0, 5)


# ── 6. MAIN WORKSPACE (5 TABS) ────────────────────────────────────────────────
st.title("Private Equity Intelligence & Due Diligence Platform")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 Deal Sourcing & Targets",
    "⚡ LBO & Covenant Simulator",
    "📄 Due Diligence RAG Copilot",
    "📊 Target Repository",
    "📈 Benchmarking & Buy-and-Build"
])

# ── TAB 1: DEAL SOURCING & TARGET DEEP-DIVE ──────────────────────────────────
with tab1:
    st.subheader("Automated Target SME Analysis")
    st.markdown("Enter a company domain or URL to trigger web scraping, structured LLM extraction, and dynamic **PE Target Score** computation.")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        target_url = st.text_input(
            "Company URL:",
            placeholder="https://example-sme.com",
            label_visibility="collapsed"
        )
    with col_btn:
        analyze_btn = st.button("🚀 Analyze Target", use_container_width=True)

    if analyze_btn and target_url:
        with st.spinner("Scraping website, executing LLM extraction, and calculating dynamic scoring..."):
            try:
                result = api_client.analyze_company(target_url)
                if result.get("status") == "SUCCESS":
                    st.success(f"Analysis completed for {result['domain']}")

                    profile = result["profile"]
                    
                    # Calculate dynamic score with active session mandate
                    dyn_scoring = recalculate_dynamic_score(profile, active_mandate)

                    # Executive Profile Card
                    with st.container(border=True):
                        st.markdown(f"### Executive Profile: **{profile.get('company_name', result['domain'])}**")
                        st.markdown(f"*{profile.get('core_activity', 'No description available')}.*")
                        st.markdown("---")

                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("PE Target Score", f"{dyn_scoring['total_score']} / 100")
                        m2.metric("Priority Tier", format_tier_badge(dyn_scoring['tier']))
                        m3.metric("Business Model", format_business_model(profile.get("business_model", "N/A")))
                        m4.metric("Estimated Scale", format_estimated_scale(profile.get("estimated_scale", "N/A")))

                        st.progress(dyn_scoring["total_score"] / 100.0, text=f"M&A Suitability: {dyn_scoring['total_score']}%")

                    st.markdown(" ")

                    # Side-by-Side Detail Sections
                    col_left, col_right = st.columns(2)

                    with col_left:
                        with st.container(border=True):
                            st.subheader("💡 Investment Thesis & Strengths")
                            for strength in profile.get("investment_thesis", {}).get("key_strengths", []):
                                st.markdown(f"• **Strength:** {strength}")
                            st.markdown("---")
                            st.markdown(f"**IC Summary:**\n{profile.get('investment_thesis', {}).get('reasoning_summary', 'N/A')}")

                    with col_right:
                        with st.container(border=True):
                            st.subheader("⚠️ Operational Risks & Breakdown")
                            for risk in profile.get("investment_thesis", {}).get("operational_risks", []):
                                st.markdown(f"• **Risk:** {risk}")
                            st.markdown("---")
                            st.caption("Points per Pillar (Active Mandate Weighting):")
                            breakdown = dyn_scoring.get("score_breakdown", {})
                            if dyn_scoring.get("knocked_out"):
                                st.error(f"🚫 Knockout: {dyn_scoring.get('knockout_reason', 'Active deal-breaker filter')}")
                            elif breakdown:
                                for label, pts in breakdown.items():
                                    st.metric(label, f"{pts:.1f} pts")
                            else:
                                st.info("No active criteria to display.")

                    # Contact & Direct Outreach Channels
                    contact_email = result.get("contact_email")
                    social_links = result.get("social_links", [])

                    with st.container(border=True):
                        st.markdown("#### 📬 Contact & Direct Outreach Channels")
                        c_mail, c_social = st.columns(2)
                        with c_mail:
                            if contact_email:
                                st.markdown(f"**📧 Contact Email:** [{contact_email}](mailto:{contact_email})")
                            else:
                                st.markdown("**📧 Contact Email:** *No email detected on website*")
                        with c_social:
                            if social_links:
                                st.markdown("**🌐 Digital Presence:**")
                                badges = []
                                for s_link in social_links:
                                    net_name = "LinkedIn" if "linkedin.com" in s_link else "Twitter/X" if any(x in s_link for x in ["twitter.com", "x.com"]) else "Instagram" if "instagram.com" in s_link else "Facebook" if "facebook.com" in s_link else "Web"
                                    badges.append(f"[{net_name}]({s_link})")
                                st.markdown(" • ".join(badges))
                            else:
                                st.markdown("**🌐 Digital Presence:** *No social profiles detected*")

                    # Download Investment Teaser Button
                    try:
                        pdf_out_path = f"data/reports/{result['domain']}_one_pager.pdf"
                        ICReportGenerator.generate_one_pager_pdf(
                            domain=result['domain'],
                            profile=profile,
                            scoring=dyn_scoring,
                            output_path=pdf_out_path,
                            contact_email=contact_email,
                            social_links=social_links,
                        )
                        if os.path.exists(pdf_out_path):
                            with open(pdf_out_path, "rb") as pdf_file:
                                st.download_button(
                                    label="📄 Download Investment Teaser (PDF)",
                                    data=pdf_file,
                                    file_name=f"IC_Teaser_{result['domain']}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                    except Exception as pdf_err:
                        st.warning(f"PDF generation notice: {str(pdf_err)}")
                else:
                    st.error(f"Analysis error: {result.get('error')}")
            except Exception as e:
                st.error(f"Error connecting to API: {str(e)}")


# ── TAB 2: LBO SIMULATOR & COVENANT STRESS ──────────────────────────────────
with tab2:
    st.subheader("⚡ LBO Stress Simulator & Debt Covenant Headroom")
    st.markdown(
        "Models the impact of **Degree of Operating Leverage (DOL)** across demand shock scenarios (-5% to -20%) "
        "and evaluates capital structure solvency and **Net Debt / EBITDA** leverage covenants."
    )

    with st.container(border=True):
        st.markdown("#### 📊 Capital Structure Parameters")
        c1, c2, c3 = st.columns(3)
        with c1:
            sim_revenue = st.number_input("Base Revenue ($/€):", min_value=100_000.0, value=8_000_000.0, step=250_000.0, format="%.2f")
            sim_covenant = st.number_input("Max Covenant Limit (Net Debt / EBITDA x):", min_value=1.0, max_value=6.0, value=3.0, step=0.25)
        with c2:
            sim_ebitda = st.number_input("Base EBITDA ($/€):", min_value=10_000.0, value=1_600_000.0, step=50_000.0, format="%.2f")
            sim_fixed_costs = st.slider("Fixed Cost Structure (%):", 0.10, 0.90, 0.60, 0.05)
        with c3:
            sim_net_debt = st.number_input("Net Debt ($/€):", value=3_200_000.0, step=100_000.0, format="%.2f")
            sim_debt_service = st.number_input("Annual Debt Service ($/€, 0=estimate 15%):", min_value=0.0, value=480_000.0, step=20_000.0, format="%.2f")

        run_sim_btn = st.button("📈 Run Sensitivity Simulation", use_container_width=True)

    if run_sim_btn or "last_sim_result" in st.session_state:
        if run_sim_btn:
            with st.spinner("Computing LBO sensitivity matrix in backend..."):
                try:
                    sim_res = api_client.simulate_leverage(
                        revenue=sim_revenue,
                        ebitda=sim_ebitda,
                        net_debt=sim_net_debt,
                        max_covenant_ratio=sim_covenant,
                        fixed_cost_ratio=sim_fixed_costs,
                        annual_debt_service=sim_debt_service if sim_debt_service > 0 else None,
                    )
                    st.session_state["last_sim_result"] = sim_res
                except Exception as sim_err:
                    st.error(f"Simulation error: {str(sim_err)}")

        if "last_sim_result" in st.session_state:
            sim_data = st.session_state["last_sim_result"]
            scenarios = sim_data.get("scenarios", [])

            # Scenarios Table
            df_scenarios = pd.DataFrame(scenarios)
            df_scenarios.rename(columns={
                "revenue_shock_pct": "Sales Drop",
                "simulated_revenue_k": "Revenue (k)",
                "simulated_ebitda_k": "EBITDA (k)",
                "simulated_cfads_k": "CFADS (k)",
                "simulated_ebitda_margin_pct": "EBITDA Margin %",
                "simulated_leverage_ratio": "Net Debt / EBITDA Ratio",
                "covenant_headroom_pct": "Covenant Headroom %",
                "dscr_ratio": "DSCR CFADS (x)",
                "covenant_breached": "Covenant Status"
            }, inplace=True)

            # Format Covenant Breached Status
            df_scenarios["Covenant Status"] = df_scenarios["Covenant Status"].apply(
                lambda x: "🔴 BREACHED" if x else "🟢 Compliant"
            )

            st.markdown("### 📋 LBO Sensitivity Matrix Results")
            display_cols = [
                "Sales Drop", "Revenue (k)", "EBITDA (k)", "CFADS (k)", "EBITDA Margin %",
                "Net Debt / EBITDA Ratio", "Covenant Headroom %", "DSCR CFADS (x)", "Covenant Status"
            ]
            # Filter existing columns
            available_cols = [c for c in display_cols if c in df_scenarios.columns]
            st.dataframe(
                df_scenarios[available_cols],
                use_container_width=True,
                hide_index=True
            )


# ── TAB 3: DUE DILIGENCE RAG COPILOT ─────────────────────────────────────────
with tab3:
    st.subheader("Financial Due Diligence Copilot (Data Room RAG)")
    col_upload, col_chat = st.columns([1, 2])

    if "indexed_targets" not in st.session_state:
        st.session_state.indexed_targets = ["logistics-veloz.com"]

    with col_upload:
        with st.container(border=True):
            st.markdown("### 📥 Document Ingestion")
            
            upload_domain = st.text_input(
                "Associated Target Domain:",
                value=target_domain_filter if target_domain_filter else "logistics-veloz.com",
                help="Domain or identifier used to isolate the Data Room for this target."
            )
            
            uploaded_file = st.file_uploader(
                "Upload Memorandum (CIM / Audit PDF):",
                type=["pdf"]
            )

            if st.button("📤 Index in Qdrant Vector DB", use_container_width=True):
                if uploaded_file:
                    target_to_use = upload_domain.strip().lower() if upload_domain else "global"
                    with st.spinner("Extracting structured balances and vectorizing..."):
                        try:
                            res = api_client.upload_document(
                                company_domain=target_to_use,
                                file_bytes=uploaded_file.getvalue(),
                                filename=uploaded_file.name,
                            )
                            if target_to_use not in st.session_state.indexed_targets:
                                st.session_state.indexed_targets.append(target_to_use)
                            st.success(
                                f"✅ Indexed: **{res['chunks_indexed']} chunks** ({res['total_pages']} pages) for `{target_to_use}`."
                            )
                        except Exception as e:
                            st.error(f"Upload error: {str(e)}")
                else:
                    st.warning("Please select a PDF file to index.")

            st.markdown("---")
            if st.button("🗑️ Clear Chat History", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()

    with col_chat:
        st.markdown("### 💬 Financial & Contractual Due Diligence Inquiries")

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "citations" in msg and msg["citations"]:
                    with st.expander("📌 View Source Citations & Evidence"):
                        for c in msg["citations"]:
                            st.markdown(
                                f"<span class='citation-badge'>Page {c['page_number']} | Similarity: {c['score']}</span>",
                                unsafe_allow_html=True
                            )
                            st.caption(f"_{c['excerpt']}_")

        user_query = st.chat_input("Ask about normalized EBITDA, bank covenants, or Change of Control clauses...")
        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.write(user_query)

            with st.chat_message("assistant"):
                with st.spinner("Querying Vector DB and synthesizing auditable answer..."):
                    try:
                        active_query_domain = upload_domain.strip() if upload_domain else None
                        rag_res = api_client.query_rag(
                            query=user_query,
                            company_domain=active_query_domain
                        )
                        answer = rag_res.get("answer", "No response.")
                        citations = rag_res.get("citations", [])

                        st.write(answer)
                        if citations:
                            with st.expander("📌 View Source Citations"):
                                for c in citations:
                                    st.markdown(
                                        f"<span class='citation-badge'>Page {c['page_number']} | Similarity: {c['score']}</span>",
                                        unsafe_allow_html=True
                                    )
                                    st.caption(f"_{c['excerpt']}_")

                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": answer,
                            "citations": citations
                        })
                    except Exception as e:
                        st.error(f"RAG query error: {str(e)}")


# ── TAB 4: TARGET REPOSITORY & DYNAMIC SCORING ────────────────────────────────
with tab4:
    st.subheader("Target SME Repository & Dynamic Scoring")
    
    try:
        companies_data = api_client.list_companies()
    except Exception as e:
        st.error(f"Error querying backend: {str(e)}")
        companies_data = []

    if companies_data:
        table_rows = []
        for item in companies_data:
            prof = item.get("profile", {})
            dyn_sc = recalculate_dynamic_score(prof, active_mandate)
            
            domain = item.get("domain", "N/A")
            if target_domain_filter and target_domain_filter.lower() not in domain.lower():
                continue
            if dyn_sc["total_score"] < min_score_filter:
                continue

            email_val = item.get("contact_email") or "—"
            s_links = item.get("social_links", [])
            s_summary = ", ".join([
                "LinkedIn" if "linkedin.com" in l else "X" if any(x in l for x in ["twitter.com", "x.com"]) else "IG" if "instagram.com" in l else "FB" if "facebook.com" in l else "Web"
                for l in s_links
            ]) if s_links else "—"

            table_rows.append({
                "Domain": domain,
                "Company": prof.get("company_name", domain),
                "Dynamic Score": dyn_sc["total_score"],
                "Tier": format_tier_badge(dyn_sc["tier"]),
                "Model": format_business_model(prof.get("business_model", "N/A")),
                "Scale": format_estimated_scale(prof.get("estimated_scale", "N/A")),
                "Contact Email": email_val,
                "Digital Presence": s_summary,
                "Buy & Build": "🟢 Yes" if prof.get("investment_thesis", {}).get("buy_and_build_potential") else "⚪ No",
                "Succession": "🟢 Yes" if prof.get("is_family_owned_or_founder_led") else "⚪ No",
            })

        if table_rows:
            df_rep = pd.DataFrame(table_rows)
            df_rep.sort_values(by="Dynamic Score", ascending=False, inplace=True)

            st.dataframe(
                df_rep,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Dynamic Score": st.column_config.ProgressColumn(
                        "Dynamic PE Score",
                        help="Normalized score from 0 to 100 based on active investment mandate",
                        format="%.1f",
                        min_value=0,
                        max_value=100,
                    ),
                    "Domain": st.column_config.TextColumn("Web Domain"),
                    "Tier": st.column_config.TextColumn("Priority Tier"),
                    "Contact Email": st.column_config.TextColumn("Outreach Email"),
                    "Digital Presence": st.column_config.TextColumn("Digital Presence"),
                }
            )
        else:
            st.info("No companies match the active filters.")
    else:
        st.info("No targets analyzed in repository yet.")


# ── TAB 5: BENCHMARKING & BUY-AND-BUILD ───────────────────────────────────────
with tab5:
    render_benchmarking_matrix(companies=companies_data)