import sys
from pathlib import Path

# Añadir la raíz del proyecto a sys.path para importar el módulo 'app' sin errores
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
import json, os

from app.ui.api_client import APIClient

st.set_page_config(
    page_title="PE Deal Sourcing & RAG Copilot",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar cliente de API y Session State
api_client = APIClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Sidebar de Configuración y Estado
st.sidebar.title("💼 PE Deal Sourcing")
st.sidebar.markdown("---")

api_status = api_client.check_health()
if api_status:
    st.sidebar.success("🟢 API Backend: Conectado")
else:
    st.sidebar.error("🔴 API Backend: Desconectado")

st.sidebar.markdown("### Parámetros de Análisis")
target_domain_filter = st.sidebar.text_input("Filtrar Target (Dominio)", placeholder="ej. logistics-veloz.com")

st.title("Plataforma de Inteligencia y Due Diligence de Private Equity")

tab1, tab2, tab3 = st.tabs([
    "🔍 Deal Sourcing & Targets",
    "📄 Due Diligence RAG Copilot",
    "📊 Repositorio de Empresas"
])

# --- TAB 1: DEAL SOURCING & TARGETS ---
with tab1:
    st.header("Análisis Automatizado de Pymes Target")
    st.markdown("Introduce la URL de una empresa para realizar el scraping, análisis LLM y cálculo del **PE Target Score**.")
    
    col_input, col_btn = st.columns([4,1])
    with col_input:
        target_url = st.text_input("URL de la Empresa:", placeholder="https://ejemplo-pyme.com", label_visibility="collapsed")
    
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

                    # Métricas principales
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("PE Target Score", f"{scoring.get('total_score', 0)} / 100")
                    m2.metric("Tier de Idoneidad", scoring.get('tier', scoring.get('target_tier', 'N/A')))
                    m3.metric("Modelo de Negocio", profile.get("business_model", "N/A"))
                    m4.metric("Escala Estimada", profile.get("estimated_scale", "N/A"))
                    st.markdown("---")
                    col_left, col_right = st.columns(2)
                    with col_left:
                        st.subheader("💡 Tesis de Inversión y Fortalezas")
                        thesis = profile.get('investment_thesis', {})
                        for strength in thesis.get('key_strengths', []):
                            st.markdown(f"• **Fortaleza:** {strength}")
                        st.markdown(f"**Resumen Ejecutivo:** {thesis.get('reasoning_summary', 'N/A')}")
                    with col_right:
                        st.subheader("⚠️ Riesgos Operativos y Desglose de Score")
                        for risk in thesis.get('operational_risks', []):
                            st.markdown(f"• **Riesgo:** {risk}")
                            
                        st.json(scoring.get("score_breakdown", {}))
                else:
                    st.error(f"Error en análisis: {result.get('error')}")
            except Exception as e:
                st.error(f"Error al conectar con la API: {str(e)}")

# --- TAB 2: DUE DILIGENCE RAG COPILOT ---
with tab2:
    st.header("Copiloto de Due Diligence Financiera (RAG)")
    col_upload, col_chat = st.columns([1, 2])

    with col_upload:
        st.subheader("Carga de Documentos (PDF)")
        upload_domain = st.text_input("Dominio de la Empresa Asociada:", value=target_domain_filter)
        uploaded_file = st.file_uploader("Cargar Memorandum (CIM / Auditoría):", type=["pdf"])
        
        if st.button("📥 Indexar en Qdrant", use_container_width=True):

            if uploaded_file and upload_domain:
                with st.spinner("Indexando documento en base de datos vectorial..."):
                    try:
                        res = api_client.upload_document(
                            company_domain=upload_domain,
                            file_bytes=uploaded_file.getvalue(),
                            filename=uploaded_file.name
                            )
                        st.success(f"Indexado con éxito: {res['chunks_indexed']} chunks creados.")
                    except Exception as e:
                        st.error(f"Error en carga: {str(e)}")
            else:
                st.warning("Indica el dominio y selecciona un archivo PDF.")

with col_chat:
    st.subheader("Consultas Conversacionales de Due Diligence")
    # Mostrar historial de chat
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "citations" in msg:
                with st.expander("📌 Ver Citas de Fuentes"):
                    for c in msg["citations"]:
                        st.caption(f"**Pág {c['page_number']}** (Score: {c['score']}): {c['excerpt']}")

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
                        "Tier": sc.get("tier", sc.get("target_tier", "N/A")),
                        "Modelo": prof.get("business_model", "N/A"),
                        "Escala": prof.get("estimated_scale", "N/A")
                    })
        if companies_data:
            df = pd.DataFrame(companies_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay empresas procesadas aún en el repositorio local.")
    else:
        st.info("Directorio de datos procesados no encontrado.")

