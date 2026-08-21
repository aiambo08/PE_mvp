import json
import os
import pandas as pd
import streamlit as st
from typing import Optional, List, Dict, Any


def format_tier_badge(tier_raw: str) -> str:
    """Maps Tier enum values to institutional color-coded badges."""
    mapping = {
        "TIER_1_HIGH_PRIORITY": "🟢 Tier 1 (High Priority)",
        "TIER_2_QUALIFIED": "🟡 Tier 2 (Qualified)",
        "TIER_3_DISCARD": "🔴 Tier 3 (Discard)",
    }
    return mapping.get(tier_raw, f"⚪ {tier_raw}")


def render_benchmarking_matrix(
    companies: Optional[List[Dict[str, Any]]] = None,
    processed_dir: str = "data/processed_json"
):
    """Renders the Side-by-Side Comparative Matrix for Buy-and-Build strategies."""
    st.subheader("📊 Buy-and-Build Comparative Matrix (Roll-Up Cockpit)")
    st.markdown(
        "Select analyzed targets to benchmark operational metrics, digital maturity signals, and consolidation fit."
    )

    available_targets: Dict[str, Dict[str, Any]] = {}

    # 1. Prioritize data provided via API or fallback to disk
    if companies:
        for data in companies:
            if data.get("status") == "SUCCESS":
                domain = data.get("domain", "N/A")
                name = data.get("profile", {}).get("company_name", domain)
                available_targets[f"{name} ({domain})"] = data
    elif os.path.exists(processed_dir):
        files = [f for f in os.listdir(processed_dir) if f.endswith(".json")]
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
            "⚠️ At least **2 analyzed companies** are required in the repository to run Buy-and-Build benchmarking."
        )
        return

    # 2. Multi-Selector (2 to 5 SMEs)
    target_keys = list(available_targets.keys())
    selected_keys = st.multiselect(
        "Select Targets to compare in Matrix:",
        options=target_keys,
        default=target_keys[:min(3, len(target_keys))],
        max_selections=5,
    )

    if len(selected_keys) < 2:
        st.info("Select at least 2 companies to activate the comparative matrix.")
        return

    selected_data = [available_targets[key] for key in selected_keys]

    # 3. Matrix Dictionary Construction
    matrix_dict = {
        "Evaluation Criterion": [
            "PE Target Score",
            "Priority Tier",
            "Business Model",
            "Estimated Scale",
            "Geographic Reach",
            "Family-Owned / Founder-Led",
            "Buy & Build Potential",
            "Client Portal / Intranet",
            "Modern Tech Stack",
            "Hiring Signals",
            "Primary Strength (IC)",
            "Primary Operational Risk",
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
        scale_val = prof.get("estimated_scale", "N/A").replace("_", " ").title()

        matrix_dict[col_header] = [
            f"{sc.get('total_score', 0)} / 100",
            format_tier_badge(tier_val),
            bm_val,
            scale_val,
            prof.get("geographic_reach", "N/A"),
            "✅ Yes"
            if prof.get("is_family_owned_or_founder_led")
            else (
                "❌ No"
                if prof.get("is_family_owned_or_founder_led") is False
                else "❓ Unknown"
            ),
            "🟢 Confirmed"
            if thesis.get("buy_and_build_potential")
            else "🔴 Low evidence",
            "✅ Yes" if ds.get("has_client_portal") else "❌ No",
            "✅ Yes" if ds.get("modern_tech_stack") else "❌ No",
            "✅ Yes" if ds.get("active_hiring_signals") else "❌ No",
            thesis.get("key_strengths", ["N/A"])[0] if thesis.get("key_strengths") else "N/A",
            thesis.get("operational_risks", ["N/A"])[0] if thesis.get("operational_risks") else "N/A",
        ]

    # 4. Convert to DataFrame and set index
    df_matrix = pd.DataFrame(matrix_dict)
    df_matrix.set_index("Evaluation Criterion", inplace=True)

    # 5. Render Matrix Side-by-Side
    with st.container(border=True):
        st.markdown("### 📋 Side-by-Side Benchmark")
        st.dataframe(
            df_matrix,
            use_container_width=True,
            height=460,
        )

    # 6. Aggregate Group Synergy Cards
    st.markdown("### 🎯 Group Synergies & Roll-Up Summary")

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

    c1.metric("Average PE Score", f"{avg_score:.1f} / 100")
    c2.metric("Buy & Build Fit", f"{buy_build_count} of {len(selected_data)}")
    c3.metric("Founder Succession", f"{family_count} of {len(selected_data)}")
    c4.metric("Digital Gap Opportunity", f"{digital_gap_count} of {len(selected_data)}")