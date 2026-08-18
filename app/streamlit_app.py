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
        "TIER_1_HIGH_PRIORITY": "🟢 Tier 1 (Alta Prioridad)",
        "TIER_2_QUALIFIED": "🟡 Tier 2 (Calificado)",
        "TIER_3_DISCARD": "🔴 Tier 3 (Descartado)",
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
        "MICRO_ENTERPRISE": "Microempresa (<10)",
        "SMALL_BUSINESS": "Pequeña Empresa (10-49)",
        "MEDIUM_BUSINESS": "Mediana Empresa (50-249)",
        "LARGE_BUSINESS": "Gran Empresa (250+)",
        "UNKNOWN": "No identificada",
    }
    return mapping.get(scale_raw, scale_raw.replace("_", " ").title())

# ── 5. SIDEBAR: THESIS CONFIGURATION DOCK ────────────────────────────────────
with st.sidebar:
    st.markdown("## 💼 PE Deal Cockpit")
    st.caption("Investment Committee Decision Terminal")
    st.markdown("---")

    # Estado de la API
    api_status = api_client.check_health()
    if api_status:
        st.success("🟢 API Backend Conectado")
    else:
        st.error("🔴 API Backend Desconectado")

    st.markdown("### ⚙️ Tesis de Inversión y Scoring")

    # ── Selector de Preset ────────────────────────────────────────────────────
    preset_names = list(THESIS_PRESETS.keys())
    selected_preset_name = st.selectbox("Preset de Inversión:", options=preset_names, index=0)
    preset_data = THESIS_PRESETS[selected_preset_name]
    st.caption(f"_{preset_data['desc']}_")

    # Detectar cambio de preset para resetear el estado de la sesión
    if st.session_state.get("_last_preset") != selected_preset_name:
        st.session_state["_last_preset"] = selected_preset_name
        st.session_state["_active_criteria"] = list(preset_data["active_criteria"])
        st.session_state["_weights"] = dict(preset_data["weights"])
        st.session_state["_knockout_b2b"] = preset_data["knockout_b2b"]
        st.session_state["_knockout_min_scale"] = preset_data["knockout_min_scale"]

    # Asegurar que el estado existe (primer render)
    if "_active_criteria" not in st.session_state:
        st.session_state["_active_criteria"] = list(preset_data["active_criteria"])
        st.session_state["_weights"] = dict(preset_data["weights"])
        st.session_state["_knockout_b2b"] = preset_data["knockout_b2b"]
        st.session_state["_knockout_min_scale"] = preset_data["knockout_min_scale"]

    with st.expander("🛠️ Personalizar Mandato de Inversión", expanded=False):

        # ── Sección 1: Deal-Breakers (Filtros Eliminatorios) ──────────────────
        st.markdown("**🚫 Filtros Eliminatorios (Deal-Breakers)**")
        knockout_b2b = st.checkbox(
            "Obligatorio B2B (descarta B2C y modelos desconocidos)",
            value=st.session_state["_knockout_b2b"],
            key="_knockout_b2b"
        )

        scale_options = {
            "Sin mínimo de escala": None,
            "Mínimo: Pequeña Empresa (10-49 FTEs)": "SMALL_BUSINESS",
            "Mínimo: Mediana Empresa (50-249 FTEs)": "MEDIUM_BUSINESS",
        }
        current_min_scale = st.session_state["_knockout_min_scale"]
        # Map stored value back to label for selectbox default
        default_scale_label = next(
            (lbl for lbl, val in scale_options.items() if val == current_min_scale),
            "Sin mínimo de escala"
        )
        selected_scale_label = st.selectbox(
            "Escala mínima requerida:",
            options=list(scale_options.keys()),
            index=list(scale_options.keys()).index(default_scale_label)
        )
        knockout_min_scale = scale_options[selected_scale_label]

        st.markdown("---")

        # ── Sección 2: Criterios Activos (Multiselect) ────────────────────────
        st.markdown("**📐 Criterios de Scoring Activos**")
        all_criteria_keys = list(SCORING_CRITERIA.keys())
        criteria_labels = {k: f"{SCORING_CRITERIA[k]['icon']} {SCORING_CRITERIA[k]['label']}" for k in all_criteria_keys}

        selected_labels = st.multiselect(
            "Dimensiones a evaluar:",
            options=[criteria_labels[k] for k in all_criteria_keys],
            default=[criteria_labels[k] for k in st.session_state["_active_criteria"] if k in criteria_labels],
            help="Selecciona las dimensiones a ponderar. Los pesos se normalizan automáticamente al 100%."
        )
        # Reverse-map labels back to keys
        label_to_key = {v: k for k, v in criteria_labels.items()}
        active_criteria = [label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key]

        if not active_criteria:
            st.warning("⚠️ Selecciona al menos un criterio para calcular el scoring.")
            active_criteria = list(preset_data["active_criteria"])  # fallback


        st.markdown("---")

        # ── Sección 3: Sliders Dinámicos (solo criterios activos) ─────────────
        st.markdown("**⚖️ Ponderaciones (%)**")
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
            st.warning("⚠️ Los pesos no pueden ser todos 0.")
            total_w = 1
        if total_w != 100:
            st.warning(f"⚠️ Suma: **{total_w}%** → Normalizado a 100% automáticamente")
        else:
            st.success("Ponderación al 100% ✅")

        # Persistir el estado de pesos para este preset
        st.session_state["_weights"] = raw_weights

    # ── Construir el mandato activo ───────────────────────────────────────────
    active_mandate = InvestmentMandateConfig(
        active_criteria=active_criteria,
        weights=raw_weights,
        knockout_b2b=knockout_b2b,
        knockout_min_scale=knockout_min_scale,
    )

    st.markdown("---")
    st.markdown("### 🎯 Filtros Rápidos")
    target_domain_filter = st.text_input("Filtrar Target por Dominio:", placeholder="ej. websbarcelona.com")
    min_score_filter = st.slider("Puntuación Mínima (Cut-off):", 0, 90, 0, 5)


# ── 6. ESPACIO DE TRABAJO PRINCIPAL (5 TABS) ─────────────────────────────────
st.title("Plataforma de Inteligencia y Due Diligence de Private Equity")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 Deal Sourcing & Targets",
    "⚡ Simulador LBO & Covenants",
    "📄 Due Diligence RAG Copilot",
    "📊 Repositorio de Empresas",
    "📈 Benchmarking & Buy-and-Build"
])

# ── TAB 1: DEAL SOURCING & TARGET DEEP-DIVE ──────────────────────────────────
with tab1:
    st.subheader("Análisis Automatizado de Pymes Target")
    st.markdown("Introduce la URL de una empresa para ejecutar el scraping web, extracción LLM estructurada y cálculo del **PE Target Score**.")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        target_url = st.text_input(
            "URL de la Empresa:",
            placeholder="https://ejemplo-pyme.com",
            label_visibility="collapsed"
        )
    with col_btn:
        analyze_btn = st.button("🚀 Analizar Target", use_container_width=True)

    if analyze_btn and target_url:
        with st.spinner("Scrapeando sitio web, ejecutando extracción LLM y calculando scoring dinámico..."):
            try:
                result = api_client.analyze_company(target_url)
                if result.get("status") == "SUCCESS":
                    st.success(f"Análisis completado para {result['domain']}")

                    profile = result["profile"]
                    
                    # Calcular scoring dinámico con el mandato activo de la sesión
                    dyn_scoring = recalculate_dynamic_score(profile, active_mandate)

                    # Tarjeta de Métricas Ejecutivas
                    with st.container(border=True):
                        st.markdown(f"### Perfil Ejecutivo: **{profile.get('company_name', result['domain'])}**")
                        st.markdown(f"*{profile.get('core_activity', 'Sin descripción')}.*")
                        st.markdown("---")

                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("PE Target Score", f"{dyn_scoring['total_score']} / 100")
                        m2.metric("Tier de Idoneidad", format_tier_badge(dyn_scoring['tier']))
                        m3.metric("Modelo de Negocio", format_business_model(profile.get("business_model", "N/A")))
                        m4.metric("Escala Estimada", format_estimated_scale(profile.get("estimated_scale", "N/A")))

                        st.progress(dyn_scoring["total_score"] / 100.0, text=f"Idoneidad M&A: {dyn_scoring['total_score']}%")

                    st.markdown(" ")

                    # Secciones de Detalle Lado a Lado
                    col_left, col_right = st.columns(2)

                    with col_left:
                        with st.container(border=True):
                            st.subheader("💡 Tesis de Inversión y Fortalezas")
                            for strength in profile.get("investment_thesis", {}).get("key_strengths", []):
                                st.markdown(f"• **Fortaleza:** {strength}")
                            st.markdown("---")
                            st.markdown(f"**Resumen para el IC:**\n{profile.get('investment_thesis', {}).get('reasoning_summary', 'N/A')}")

                    with col_right:
                        with st.container(border=True):
                            st.subheader("⚠️ Riesgos Operativos y Desglose")
                            for risk in profile.get("investment_thesis", {}).get("operational_risks", []):
                                st.markdown(f"• **Riesgo:** {risk}")
                            st.markdown("---")
                            st.caption("Puntos por Pilar (Ponderación Dinámica Activa):")
                            breakdown = dyn_scoring.get("score_breakdown", {})
                            if dyn_scoring.get("knocked_out"):
                                st.error(f"🚫 Knockout: {dyn_scoring.get('knockout_reason', 'Filtro eliminatorio activo')}")
                            elif breakdown:
                                for label, pts in breakdown.items():
                                    st.metric(label, f"{pts:.1f} pts")
                            else:
                                st.info("Sin criterios activos para mostrar.")

                    # Botón de Descarga de Teaser PDF
                    try:
                        pdf_out_path = f"data/reports/{result['domain']}_one_pager.pdf"
                        ICReportGenerator.generate_one_pager_pdf(
                            domain=result['domain'],
                            profile=profile,
                            scoring=dyn_scoring,
                            output_path=pdf_out_path
                        )
                        if os.path.exists(pdf_out_path):
                            with open(pdf_out_path, "rb") as pdf_file:
                                st.download_button(
                                    label="📄 Descargar Investment Teaser (PDF)",
                                    data=pdf_file,
                                    file_name=f"IC_Teaser_{result['domain']}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                    except Exception as pdf_err:
                        st.warning(f"Aviso en generación PDF: {str(pdf_err)}")
                else:
                    st.error(f"Error en análisis: {result.get('error')}")
            except Exception as e:
                st.error(f"Error al conectar con la API: {str(e)}")


# ── TAB 2: SIMULADOR LBO & ESTRÉS DE COVENANTS ──────────────────────────────
with tab2:
    st.subheader("⚡ Simulador de Estrés LBO & Rotura de Covenants Bancarios")
    st.markdown(
        "Modela el impacto del **Apalancamiento Operativo (DOL)** ante caídas de demanda (-5% a -20%) "
        "y evalúa la solvencia de la estructura de capital y el ratio **DFN / EBITDA**."
    )

    with st.container(border=True):
        st.markdown("#### 📊 Parámetros de la Estructura Financiera")
        c1, c2, c3 = st.columns(3)
        with c1:
            sim_revenue = st.number_input("Facturación Base (€):", min_value=100_000.0, value=8_000_000.0, step=250_000.0, format="%.2f")
            sim_covenant = st.number_input("Límite Covenant DFN/EBITDA (x):", min_value=1.0, max_value=6.0, value=3.0, step=0.25)
        with c2:
            sim_ebitda = st.number_input("EBITDA Base (€):", min_value=10_000.0, value=1_600_000.0, step=50_000.0, format="%.2f")
            sim_fixed_costs = st.slider("Estructura de Costes Fijos (%):", 0.10, 0.90, 0.60, 0.05)
        with c3:
            sim_net_debt = st.number_input("Deuda Financiera Neta (€):", value=3_200_000.0, step=100_000.0, format="%.2f")
            sim_debt_service = st.number_input("Servicio Anual Deuda (€, 0=estimar 15%):", min_value=0.0, value=480_000.0, step=20_000.0, format="%.2f")

        run_sim_btn = st.button("📈 Ejecutar Simulación de Sensibilidad", use_container_width=True)

    if run_sim_btn or "last_sim_result" in st.session_state:
        if run_sim_btn:
            with st.spinner("Calculando sensibilidad LBO en backend..."):
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
                    st.error(f"Error en simulación: {str(sim_err)}")

        if "last_sim_result" in st.session_state:
            sim_data = st.session_state["last_sim_result"]
            scenarios = sim_data.get("scenarios", [])

            # Tabla de Escenarios
            df_scenarios = pd.DataFrame(scenarios)
            df_scenarios.rename(columns={
                "revenue_shock_pct": "Caída Ventas",
                "simulated_revenue_k": "Ventas (k€)",
                "simulated_ebitda_k": "EBITDA (k€)",
                "simulated_cfads_k": "CFADS (k€)",
                "simulated_ebitda_margin_pct": "Margen EBITDA %",
                "simulated_leverage_ratio": "Ratio DFN/EBITDA",
                "covenant_headroom_pct": "Holgura Covenant %",
                "dscr_ratio": "DSCR CFADS (x)",
                "covenant_breached": "Rotura Covenant"
            }, inplace=True)

            # Formateo de Rotura de Covenant
            df_scenarios["Rotura Covenant"] = df_scenarios["Rotura Covenant"].apply(
                lambda x: "🔴 INCUMPLIDO" if x else "🟢 Cumplido"
            )

            st.markdown("### 📋 Resultados de la Matriz de Sensibilidad LBO")
            display_cols = [
                "Caída Ventas", "Ventas (k€)", "EBITDA (k€)", "CFADS (k€)", "Margen EBITDA %",
                "Ratio DFN/EBITDA", "Holgura Covenant %", "DSCR CFADS (x)", "Rotura Covenant"
            ]
            # Filtrar solo columnas existentes
            available_cols = [c for c in display_cols if c in df_scenarios.columns]
            st.dataframe(
                df_scenarios[available_cols],
                use_container_width=True,
                hide_index=True
            )


# ── TAB 3: DUE DILIGENCE RAG COPILOT ─────────────────────────────────────────
with tab3:
    st.subheader("Copiloto de Due Diligence Financiera (RAG Anti-Alucinación)")
    col_upload, col_chat = st.columns([1, 2])

    with col_upload:
        with st.container(border=True):
            st.markdown("### 📥 Ingesta de Documentos")
            upload_domain = st.text_input(
                "Dominio Target Asociado:",
                value=target_domain_filter if target_domain_filter else ""
            )
            uploaded_file = st.file_uploader(
                "Cargar Memorandum (CIM / Auditoría PDF):",
                type=["pdf"]
            )

            if st.button("📤 Indexar en Qdrant Vector DB", use_container_width=True):
                if uploaded_file and upload_domain:
                    with st.spinner("Extrayendo tablas estructuradas en Markdown y vectorizando..."):
                        try:
                            res = api_client.upload_document(
                                company_domain=upload_domain,
                                file_bytes=uploaded_file.getvalue(),
                                filename=uploaded_file.name,
                            )
                            st.success(
                                f"Indexado correctamente: **{res['chunks_indexed']} chunks** ({res['total_pages']} págs)."
                            )
                        except Exception as e:
                            st.error(f"Error en carga: {str(e)}")
                else:
                    st.warning("Indica el dominio e introduce un archivo PDF.")

    with col_chat:
        st.markdown("### 💬 Consultas Financieras y Contractuales")

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "citations" in msg and msg["citations"]:
                    with st.expander("📌 Ver Citas de Fuentes y Evidencias"):
                        for c in msg["citations"]:
                            st.markdown(
                                f"<span class='citation-badge'>Pág. {c['page_number']} | Score: {c['score']}</span>",
                                unsafe_allow_html=True
                            )
                            st.caption(f"_{c['excerpt']}_")

        user_query = st.chat_input("Pregunta sobre EBITDA normalizado, covenants bancarios o cláusulas Change of Control...")
        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.write(user_query)

            with st.chat_message("assistant"):
                with st.spinner("Consultando Vector DB y procesando respuesta auditable..."):
                    try:
                        rag_res = api_client.query_rag(
                            query=user_query,
                            company_domain=upload_domain if upload_domain else None
                        )
                        answer = rag_res.get("answer", "Sin respuesta.")
                        citations = rag_res.get("citations", [])

                        st.write(answer)
                        if citations:
                            with st.expander("📌 Ver Citas de Fuentes"):
                                for c in citations:
                                    st.markdown(
                                        f"<span class='citation-badge'>Pág. {c['page_number']} | Similitud: {c['score']}</span>",
                                        unsafe_allow_html=True
                                    )
                                    st.caption(f"_{c['excerpt']}_")

                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": answer,
                            "citations": citations
                        })
                    except Exception as e:
                        st.error(f"Error en consulta RAG: {str(e)}")


# ── TAB 4: REPOSITORIO DINÁMICO DE TARGETS ───────────────────────────────────
with tab4:
    st.subheader("Repositorio de Pymes y Scoring Dinámico")
    
    try:
        companies_data = api_client.list_companies()
    except Exception as e:
        st.error(f"Error consultando backend: {str(e)}")
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

            table_rows.append({
                "Dominio": domain,
                "Empresa": prof.get("company_name", domain),
                "Score Dinámico": dyn_sc["total_score"],
                "Tier": format_tier_badge(dyn_sc["tier"]),
                "Modelo": format_business_model(prof.get("business_model", "N/A")),
                "Escala": format_estimated_scale(prof.get("estimated_scale", "N/A")),
                "Buy & Build": "🟢 Sí" if prof.get("investment_thesis", {}).get("buy_and_build_potential") else "⚪ No",
                "Relevo Gen.": "🟢 Sí" if prof.get("is_family_owned_or_founder_led") else "⚪ No",
            })

        if table_rows:
            df_rep = pd.DataFrame(table_rows)
            df_rep.sort_values(by="Score Dinámico", ascending=False, inplace=True)

            st.dataframe(
                df_rep,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score Dinámico": st.column_config.ProgressColumn(
                        "PE Score Dinámico",
                        help="Puntuación normalizada de 0 a 100 según la tesis activa",
                        format="%.1f",
                        min_value=0,
                        max_value=100,
                    ),
                    "Dominio": st.column_config.TextColumn("Dominio Web"),
                    "Tier": st.column_config.TextColumn("Tier de Prioridad"),
                }
            )
        else:
            st.info("No hay empresas que cumplan los filtros activos.")
    else:
        st.info("No hay targets analizados aún en el repositorio.")


# ── TAB 5: BENCHMARKING & BUY-AND-BUILD ───────────────────────────────────────
with tab5:
    render_benchmarking_matrix(companies=companies_data)