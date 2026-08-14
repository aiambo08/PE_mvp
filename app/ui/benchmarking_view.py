import json
import os
import pandas as pd
import streamlit as st


def format_tier_badge(tier_raw: str) -> str:
    """Mapea los enumerados de Tier a badges con código de color."""
    mapping = {
        "TIER_1_HIGH_PRIORITY": "🟢 Tier 1 (Alta Prioridad)",
        "TIER_2_QUALIFIED": "🟡 Tier 2 (Calificado)",
        "TIER_3_DISCARD": "🔴 Tier 3 (Descartado)",
    }
    return mapping.get(tier_raw, f"⚪ {tier_raw}")


def render_benchmarking_matrix(processed_dir: str = "data/processed_json"):
    """Renderiza la Matriz Comparativa Lado a Lado para estrategias Buy-and-Build."""
    st.subheader("📊 Matriz Comparativa Buy-and-Build (Roll-Up Matrix)")
    st.markdown(
        "Selecciona Pymes analizadas para comparar sus métricas operativas, grado de digitalización y encaje de consolidación inorgánica."
    )

    if not os.path.exists(processed_dir):
        st.info("No existe el directorio de datos procesados.")
        return

    # 1. Cargar targets disponibles en disco
    files = [f for f in os.listdir(processed_dir) if f.endswith(".json")]
    available_targets = {}

    for file in files:
        filepath = os.path.join(processed_dir, file)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("status") == "SUCCESS":
                domain = data["domain"]
                name = data["profile"]["company_name"]
                available_targets[f"{name} ({domain})"] = data

    if len(available_targets) < 2:
        st.warning(
            "⚠️ Se necesitan al menos **2 empresas analizadas** en el repositorio para realizar una comparación Buy-and-Build."
        )
        return

    # 2. Selector Múltiple (2 a 5 Pymes)
    selected_keys = st.multiselect(
        "Selecciona los Targets a comparar:",
        options=list(available_targets.keys()),
        default=list(available_targets.keys())[:3],
        max_selections=5,
    )

    if len(selected_keys) < 2:
        st.info("Selecciona al menos 2 empresas para activar la matriz comparativa.")
        return

    selected_data = [available_targets[key] for key in selected_keys]

    # 3. Construcción del Diccionario de la Matriz (Criterios en filas, Empresas en columnas)
    matrix_dict = {
        "Criterio de Evaluación": [
            "PE Target Score",
            "Tier de Prioridad",
            "Modelo de Negocio",
            "Escala Estimada",
            "Alcance Geográfico",
            "Empresa Familiar / Fundador",
            "Potencial Buy & Build",
            "Portal Cliente / Intranet",
            "Tech Stack Moderno",
            "Señales de Contratación",
            "Fortaleza Principal",
            "Riesgo Operativo Principal",
        ]
    }

    for target in selected_data:
        prof = target.get("profile", {})
        sc = target.get("scoring", {})
        ds = prof.get("digital_signals", {})
        thesis = prof.get("investment_thesis", {})

        col_header = f"🏢 {prof.get('company_name', 'N/A')}\n({target.get('domain', 'N/A')})"
        tier_val = sc.get("tier", sc.get("target_tier", "N/A"))
        bm_val = prof.get("business_model", "N/A").replace("_", " ").title()
        scale_val = prof.get("estimated_scale", "N/A").title()

        matrix_dict[col_header] = [
            f"{sc.get('total_score', 0)} / 100",
            format_tier_badge(tier_val),
            bm_val,
            scale_val,
            prof.get("geographic_reach", "N/A"),
            "✅ Sí"
            if prof.get("is_family_owned_or_founder_led")
            else (
                "❌ No"
                if prof.get("is_family_owned_or_founder_led") is False
                else "❓ Indeterminado"
            ),
            "🟢 Confirmado"
            if thesis.get("buy_and_build_potential")
            else "🔴 No evidente",
            "✅ Sí" if ds.get("has_client_portal") else "❌ No",
            "✅ Sí" if ds.get("modern_tech_stack") else "❌ No",
            "✅ Sí" if ds.get("active_hiring_signals") else "❌ No",
            thesis.get("key_strengths", ["N/A"])[0] if thesis.get("key_strengths") else "N/A",
            thesis.get("operational_risks", ["N/A"])[0]
            if thesis.get("operational_risks")
            else "N/A",
        ]

    # 4. Convertir a DataFrame y fijar índice
    df_matrix = pd.DataFrame(matrix_dict)
    df_matrix.set_index("Criterio de Evaluación", inplace=True)

    # 5. Renderizar la Matriz Lado a Lado
    with st.container(border=True):
        st.markdown("### 📋 Comparativa Lado a Lado")
        st.dataframe(
            df_matrix,
            use_container_width=True,
            height=460,
        )

    # 6. Tarjetas de Métricas Agregadas y Sinergias del Grupo
    st.markdown("### 🎯 Sinergias de Grupo & Resumen del Roll-Up")

    c1, c2, c3, c4 = st.columns(4)

    avg_score = sum(t.get("scoring", {}).get("total_score", 0) for t in selected_data) / len(
        selected_data
    )
    buy_build_count = sum(
        1
        for t in selected_data
        if t.get("profile", {}).get("investment_thesis", {}).get("buy_and_build_potential")
    )
    family_count = sum(
        1
        for t in selected_data
        if t.get("profile", {}).get("is_family_owned_or_founder_led")
    )
    digital_gap_count = sum(
        1
        for t in selected_data
        if not t.get("profile", {}).get("digital_signals", {}).get("modern_tech_stack")
    )

    c1.metric("PE Score Promedio", f"{avg_score:.1f} / 100")
    c2.metric("Aptas para Buy & Build", f"{buy_build_count} de {len(selected_data)}")
    c3.metric("Relevo Generacional (Familia)", f"{family_count} de {len(selected_data)}")
    c4.metric("Oportunidad Gap Digital", f"{digital_gap_count} de {len(selected_data)}")