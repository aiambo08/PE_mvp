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

from app.ui.api_client import APIClient
from app.services.report_service import ICReportGenerator
from app.ui.benchmarking_view import render_benchmarking_matrix

# 1. Configuración de la página
st.set_page_config(
    page_title="PE Deal Sourcing & RAG Copilot",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inyección de CSS personalizado
CUSTOM_CSS = """
<style>
    /* Estilo de fuentes y espaciado general */
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Encabezados y títulos */
    h1,
    h2,
    h3 {
        letter-spacing: -0.5px;
    }

    /* Rediseño de tarjetas Metric */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #3b82f6 !important;
    }

    /* Ajuste de contenedores bordeados */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px !important;
        border: 1px solid #334155 !important;
        background-color: #0f172a20 !important;
        padding: 12px !important;
        }

    /* Botones primarios */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out;
    }

    /* Ajuste del área de Chat */
    .stChatMessage {
        border-radius: 10px !important;
        padding: 12px !important;
        margin-bottom: 8px !important;
    }

</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# 3. Inicializar cliente de API y Session State
api_client = APIClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Funciones auxiliares de formateo visual
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
    mapping = {
        "B2B_SAAS": "B2B SaaS",
        "B2B_PRODUCT": "B2B Producto",
        "B2B_SERVICES": "B2B Servicios",
        "B2B_MARKETPLACE": "B2B Marketplace",
        "B2C": "B2C",
        "B2C_SAAS": "B2C SaaS",
        "B2C_PRODUCT": "B2C Producto",
        "B2C_SERVICES": "B2C Servicios",
    }
    return mapping.get(bm_raw, bm_raw.replace("_", " ").title())

def format_estimated_scale(scale_raw: str) -> str:
    if not scale_raw or scale_raw == "N/A":
        return "N/A"
    mapping = {
        "MICRO_ENTERPRISE": "Microempresa",
        "SMALL_BUSINESS": "Pequeña Empresa",
        "MEDIUM_BUSINESS": "Mediana Empresa",
        "LARGE_BUSINESS": "Gran Empresa",
        "UNKNOWN": "No especificada",
    }
    return mapping.get(scale_raw, scale_raw.replace("_", " ").title())

# Sidebar de Configuración y Estado
st.sidebar.title("💼 PE Deal Sourcing")
st.sidebar.markdown("---")

api_status = api_client.check_health()
if api_status:
    st.sidebar.success("🟢 API Backend: Conectado (FastAPI)")
else:
    st.sidebar.error("🔴 API Backend: Desconectado")

st.sidebar.markdown("### Parámetros de Análisis")
target_domain_filter = st.sidebar.text_input("Filtrar Target (Dominio)", placeholder="ej. logistics-veloz.com")

st.title("Plataforma de Inteligencia y Due Diligence de Private Equity")

tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Deal Sourcing & Targets",
    "📄 Due Diligence RAG Copilot",
    "📊 Repositorio de Empresas",
    "📈 Benchmarking & Buy-and-Build"
])

# --- TAB 1: DEAL SOURCING & TARGETS ---
with tab1:
    st.header("Análisis Automatizado de Pymes Target")
    st.markdown("Introduce la URL de una empresa para realizar el scraping, análisis LLM y cálculo del **PE Target Score**.")
    
    col_input, col_btn = st.columns([4,1])
    with col_input:
        target_url = st.text_input(
            "URL de la Empresa:", 
            placeholder="https://ejemplo-pyme.com", 
            label_visibility="collapsed")
    
    with col_btn:
        analyze_btn = st.button("🚀 Analizar Target", use_container_width=True)
    if analyze_btn and target_url:
        with st.spinner("Scrapeando sitio web, ejecutando extracción LLM local y calculando score ..."):
            try:
                result = api_client.analyze_company(target_url)
                if result.get("status") == "SUCCESS":
                    st.success(f"Análisis completado para {result['domain']}")

                    profile = result["profile"]
                    scoring = result["scoring"]

                    # Tarjeta superior de métricas
                    with st.container(border=True):
                        st.markdown(
                            f"### Perfil Ejecutivo: **{profile['company_name']}**"
                        )
                        st.markdown(f"*{profile['core_activity']}*")
                        st.markdown("---")
                    
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("PE Target Score", f"{scoring.get('total_score', 0)} / 100")
                        m2.metric("Tier de Idoneidad", format_tier_badge(scoring.get('tier', scoring.get('target_tier', 'N/A'))))
                        m3.metric("Modelo de Negocio", format_business_model(profile.get("business_model", "N/A")))
                        m4.metric("Escala Estimada", format_estimated_scale(profile.get("estimated_scale", "N/A")))

                        st.progress(
                            scoring["total_score"] /100,
                            text=f"Nivel de idoneidad: {scoring['total_score']}%",
                        )
                    st.markdown(" ")

                    # Secciones de detalle
                    col_left, col_right = st.columns(2)

                    with col_left:
                        with st.container(border=True):
                            st.subheader("💡 Tesis de Inversión y Fortalezas")
                            for strength in profile["investment_thesis"][
                                "key_strengths"
                            ]:
                                st.markdown(f"• **Fortaleza:** {strength}")

                            st.markdown("---")
                            st.markdown(
                                f"**Resumen Ejecutivo:**\n{profile['investment_thesis']['reasoning_summary']}"
                            )

                    with col_right:
                        with st.container(border=True):
                            st.subheader("⚠️ Riesgos Operativos y Scoring")
                            for risk in profile["investment_thesis"][
                                "operational_risks"
                            ]:
                                st.markdown(f"• **Riesgo:** {risk}")

                            st.markdown("---")
                            st.caption("Desglose Cuantitativo de Puntos:")
                            st.json(scoring["score_breakdown"])

                    # Botón de descarga de PDF Investment Teaser
                    try:
                        pdf_out_path = f"data/reports/{result['domain']}_one_pager.pdf"
                        ICReportGenerator.generate_one_pager_pdf(
                            domain=result['domain'],
                            profile=profile,
                            scoring=scoring,
                            output_path=pdf_out_path
                        )

                        with open(pdf_out_path, "rb") as pdf_file:
                            st.download_button(
                                label="📄 Descargar Investment Teaser (PDF)",
                                data=pdf_file,
                                file_name=f"IC_Teaser_{result['domain']}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    except Exception as pdf_err:
                        st.warning(f"No se pudo generar el PDF del Teaser: {str(pdf_err)}")
                else:
                    st.error(f"Error en análisis: {result.get('error')}")
            except Exception as e:
                st.error(f"Error al conectar con la API: {str(e)}")

# --- TAB 2: DUE DILIGENCE RAG COPILOT ---
with tab2:
    st.subheader("Copiloto de Due Diligence Financiera (RAG)")
    col_upload, col_chat = st.columns([1, 2])

    with col_upload:
        with st.container(border=True):
            st.markdown("### 📥 Ingesta de Documentos")
            upload_domain = st.text_input(
                "Dominio Target Asociado:", value=target_domain_filter
            )
            uploaded_file = st.file_uploader(
                "Cargar Memorandum (CIM / Auditoría PDF):", type=["pdf"]
            )

            if st.button(" Indexar en Qdrant Vector DB", use_container_width=True):
                if uploaded_file and upload_domain:
                    with st.spinner(
                        "Extrayendo tablas en Markdown y vectorizando..."
                    ):
                        try:
                            res = api_client.upload_document(
                                company_domain=upload_domain,
                                file_bytes=uploaded_file.getvalue(),
                                filename=uploaded_file.name,
                            )
                            st.success(
                                f"Indexado correctamente: **{res['chunks_indexed']} chunks** creados ({res['total_pages']} págs)."
                            )
                        except Exception as e:
                            st.error(f"Error en carga: {str(e)}")
                else:
                    st.warning("Indica el dominio y selecciona un archivo PDF.")

    with col_chat:
        st.markdown("### 💬 Consultas Financieras y Contractuales")

        # Display Chat History
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "citations" in msg:
                    with st.expander("📌 Ver Citas de Fuentes y Evidencias"):
                        for c in msg["citations"]:
                            st.caption(
                                f"📄 **Página {c['page_number']}** (Similitud: `{c['score']}`):\n_{c['excerpt']}_"
                            )

        # Input de pregunta
        user_query = st.chat_input("Haz una pregunta sobre los datos financieros o covenants...")
        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
        
            with st.chat_message("user"):
                st.write(user_query)

            with st.chat_message("assistant"):
                with st.spinner("Consultando Qdrant Vector DB y ejecutando Qwen2.5..."):
                    try:
                        rag_res = api_client.query_rag(
                            query=user_query,
                            company_domain=upload_domain if upload_domain else None
                        )
                        answer = rag_res["answer"]
                        citations = rag_res["citations"]
                        st.write(answer)

                        with st.expander("📌 Ver Citas de Fuentes"):
                            for c in citations:
                                st.caption(f"**Pág {c['page_number']}** (Score: {c['score']}): {c['excerpt']}")

                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": answer,
                            "citations": citations
                        })
                    except Exception as e:
                        st.error(f"Error en consulta RAG: {str(e)}")
                    
# --- TAB 3: REPOSITORIO DE TARGETS ---
with tab3:
    st.header("Repositorio de Pymes Analizadas")
    processed_dir = "data/processed_json"
    
    if os.path.exists(processed_dir):
        files = [f for f in os.listdir(processed_dir) if f.endswith(".json")]
        companies_data = []

        for file in files:
            with open(os.path.join(processed_dir, file), "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("status") == "SUCCESS":
                    prof = data.get("profile", {})
                    sc = data.get("scoring", {})
                    companies_data.append({
                        "Dominio": data.get("domain", "N/A"),
                        "Empresa": prof.get("company_name", "N/A"),
                        "PE Score": sc.get("total_score", 0),
                        "Tier": format_tier_badge(sc.get("tier", sc.get("target_tier", "N/A"))),
                        "Modelo": format_business_model(prof.get("business_model", "N/A")),
                        "Escala": format_estimated_scale(prof.get("estimated_scale", "N/A"))
                    })
        if companies_data:
            df = pd.DataFrame(companies_data)

            # Formateo enriquecido con st.column_config
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "PE Score": st.column_config.ProgressColumn(
                        "PE Target Score",
                        help="Puntuación de 0 a 100 asignada por el motor de scoring",
                        format="%d",
                        min_value=0,
                        max_value=100,
                    ),
                    "Dominio": st.column_config.TextColumn(
                        "Dominio Web",
                        help="Dominio oficial de la empresa",
                    ),
                    "Tier": st.column_config.TextColumn(
                        "Tier de Idoneidad",
                        help="Categorización de prioridad para M&A",
                    ),
                },
            )
        else:
            st.info("No hay empresas procesadas aún en el repositorio local.")
    else:
        st.info("Directorio `data/processed_json` no encontrado.")

# --- TAB 4: BENCHMARKING BUY-AND-BUILD ---
with tab4:
    render_benchmarking_matrix(processed_dir="data/processed_json")