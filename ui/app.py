"""Main Streamlit Application for the SLR Multi-Agent Pipeline."""
import re
import asyncio

import streamlit as st

st.set_page_config(
    page_title="SLR Multi-Agent Pipeline",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Agent ordering ─────────────────────────────────────────────────────────────
AGENTS = ["Prepper", "DIO", "MEL", "SIMO"]
AGENT_ICONS = {
    "Prepper": "⚙",
    "DIO":     "↗",
    "MEL":     "◈",
    "SIMO":    "≋",
}

# ── Session State ──────────────────────────────────────────────────────────────
_defaults = {
    "current_agent":           "Prepper",
    "unlocked_agents":         {"Prepper"},   # grows as pipeline progresses
    "chat_history":            [{"role": "assistant", "content": "Welcome to the Sea Level Rise Prediction System. Begin by configuring the backend connections in the Prepper panel."}],
    "handoff_token":           None,
    "artifact_token":          None,
    "simulation_results":      None,
    "parcel_value_override":   {"table": None, "column": None},
    "study_config": {
        "training_table":   "clean_data.claims_processed",
        "prediction_table": "public.parcels_cliplayer",
        "values_table":     None,
        "values_col":       None,
    },
    "pending_mel_confirmation": False,
    "mel_distributions":       None,
    "mel_predictors":          [],
    "mel_metrics":             [],
    "simo_canvas_chat":        [{"role": "assistant", "content": "Ask me anything about the flood damage simulation results."}],
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def _unlock(agent: str):
    """Mark an agent as accessible in the sidebar."""
    st.session_state.unlocked_agents.add(agent)

def _go(agent: str):
    """Navigate to an agent view."""
    _unlock(agent)
    st.session_state.current_agent = agent

# Backward-compat shim so existing view code reading active_phase still works
_PHASE_MAP = {"Prepper": 0, "DIO": 1, "MEL": 2, "SIMO": 3}
st.session_state.active_phase = _PHASE_MAP.get(st.session_state.current_agent, 0)

# ── Sidebar Navigation ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### SLR Pipeline")
    st.divider()

    unlocked = st.session_state.unlocked_agents
    for agent in AGENTS:
        if agent in unlocked:
            if st.sidebar.button(
                agent,
                use_container_width=True,
                type="primary" if st.session_state.current_agent == agent else "secondary",
                key=f"nav_{agent}",
            ):
                st.session_state.current_agent = agent
                st.session_state.active_phase = _PHASE_MAP[agent]
                st.rerun()
        else:
            st.sidebar.caption(f"  {agent}  (locked)")

    st.divider()

    # Agent status indicators
    st.markdown("**Pipeline Status**")
    st.caption(f"Handoff token: {'set' if st.session_state.handoff_token else 'pending'}")
    st.caption(f"Artifact token: {'set' if st.session_state.artifact_token else 'pending'}")
    st.caption(f"Simulation: {'run' if st.session_state.simulation_results else 'pending'}")

# ── Split-Screen Layout ────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 2])

# ── Left Panel: Conversational Orchestrator ────────────────────────────────────
with left_col:
    st.header("Agent Chat", anchor=False)

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a question or provide a command..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # ── Phase 3: Route to SIMO RAG ─────────────────────────────────────────
        if st.session_state.current_agent == "SIMO":
            with st.chat_message("assistant"):
                with st.spinner("Querying simulation knowledge base..."):
                    try:
                        from api_client import APIClient
                        client = APIClient()
                        rag_res = asyncio.run(client.simo_chat(prompt))
                        answer = rag_res.get("answer", "No answer returned.")
                    except Exception as e:
                        answer = f"RAG unavailable: {e}"
                st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

        else:
            # ── Context-aware study design parser (Phases 0-2) ─────────────────
            p_lower = prompt.lower()
            p_orig  = prompt  # preserve case for schema-qualified names

            # ── Table synonym resolver ──────────────────────────────────────────
            # Keys are bare names (no schema prefix); values are fully-qualified.
            RESOLVE_TABLES = {
                "parcels_clipped":         "public.parcels_cliplayer",
                "parcels_cliplayer":       "public.parcels_cliplayer",
                "parcels_clipped_layer":   "public.parcels_cliplayer",
                "parcels":                 "public.parcels_cliplayer",
                "property_real_value":     "public.real_property_values",
                "real_property_value":     "public.real_property_values",
                "real_property_values":    "public.real_property_values",
                "property_values":         "public.real_property_values",
                "parcel_value":            "public.real_property_values",
                "collier_county_claims":   "clean_data.collier_claims_cleaned",
                "collier_claims_cleaned":  "clean_data.collier_claims_cleaned",
                "claims_cleaned":          "clean_data.collier_claims_cleaned",
                "claims_processed":        "clean_data.claims_processed",
            }

            def resolve(raw: str) -> str:
                """Resolve a table reference to a fully-qualified name."""
                raw = raw.strip().rstrip(".,;")
                # Check for alias even if it has a schema
                lower_raw = raw.lower()
                for alias, real in RESOLVE_TABLES.items():
                    if lower_raw == alias or lower_raw == real.lower() or lower_raw == f"public.{alias}":
                        return real
                # Already fully-qualified and not a known alias → return as-is
                if "." in raw:
                    return raw
                return RESOLVE_TABLES.get(raw.lower(), f"public.{raw}")

            # ── Pattern helpers ─────────────────────────────────────────────────
            # Each field has multiple regex alternatives so natural sentences match.
            _TBL = r"([\w]+(?:\.[\w]+)?)"   # bare or schema.table

            # Training table patterns
            _TRAIN_PATS = [
                rf"using\s+{_TBL}\s+as\s+training",
                rf"training\s+(?:data|table|set)\s+(?:is\s+|in\s+|from\s+|using\s+){_TBL}",
                rf"train(?:ing)?\s+(?:on|from|with)\s+{_TBL}",
            ]
            # Prediction / target parcels patterns
            _PRED_PATS = [
                rf"apply\s+(?:that\s+)?model\s+(?:to|into|on)\s+(?:my\s+)?{_TBL}",
                rf"apply\s+(?:it\s+)?(?:to|into|on)\s+(?:my\s+)?{_TBL}",
                rf"predict\s+(?:flood\s+damage\s+)?(?:in|on|into|for)\s+{_TBL}",
                rf"(?:target|prediction)\s+(?:table\s+)?(?:is\s+)?{_TBL}",
                rf"model\s+(?:it\s+)?(?:on|into|against)\s+{_TBL}",
            ]
            # Values / property table patterns
            _VAL_PATS = [
                rf"(?:parcel\s+)?value[s]?\s+(?:can\s+be\s+)?(?:found\s+)?in\s+{_TBL}",
                rf"(?:property\s+)?value[s]?\s+(?:are\s+)?(?:in|from|at)\s+{_TBL}",
                rf"values?\s+(?:table\s+)?(?:is\s+)?{_TBL}",
            ]

            def first_match(patterns, text):
                for pat in patterns:
                    m = re.search(pat, text, re.IGNORECASE)
                    if m:
                        return m.group(1)
                return None

            # ── Extract fields ──────────────────────────────────────────────────
            raw_train = first_match(_TRAIN_PATS, p_orig)
            if raw_train:
                st.session_state.study_config["training_table"] = resolve(raw_train)

            raw_pred = first_match(_PRED_PATS, p_orig)
            if raw_pred:
                st.session_state.study_config["prediction_table"] = resolve(raw_pred)

            raw_val = first_match(_VAL_PATS, p_orig)
            if raw_val:
                resolved_val = resolve(raw_val)
                st.session_state.study_config["values_table"] = resolved_val
                # Derive sensible default column
                if "real_property_values" in resolved_val or "property_value" in resolved_val:
                    st.session_state.study_config["values_col"] = "totaljustvalue"
                else:
                    st.session_state.study_config["values_col"] = "parcel_value"

            # Proactive map centering
            conf = st.session_state.study_config
            if conf["prediction_table"]:
                try:
                    from api_client import APIClient
                    client = APIClient()
                    schema, table = (
                        conf["prediction_table"].split(".", 1)
                        if "." in conf["prediction_table"]
                        else ("public", conf["prediction_table"])
                    )
                    extent_res = asyncio.run(client.get_table_extent(table, schema))
                    if "extent" in extent_res:
                        box = extent_res["extent"]
                        m = re.search(r"BOX\(([-\d\.]+) ([-\d\.]+),([-\d\.]+) ([-\d\.]+)\)", box)
                        if m:
                            xmin, ymin, xmax, ymax = map(float, m.groups())
                            st.session_state.map_extent = [[ymin, xmin], [ymax, xmax]]
                except Exception:
                    pass

            response = "### Study Design Updated\n"
            response += f"- **Training Set:** `{conf['training_table']}`\n"
            response += f"- **Target Parcels:** `{conf['prediction_table']}`\n"
            if conf["values_table"]:
                response += f"- **Value Source:** `{conf['values_table']}.{conf['values_col']}`\n"
            response += "\nConfigured. Shall we move to **MEL** to train the models based on this setup?"

            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.session_state.pending_mel_confirmation = True
            with st.chat_message("assistant"):
                st.markdown(response)

    # Persistent MEL confirmation button
    if st.session_state.get("pending_mel_confirmation") and st.session_state.current_agent == "DIO":
        with st.chat_message("assistant"):
            st.info("Study configuration is ready.")
            if st.button("Confirm and Proceed to MEL Training", key="proceed_btn_fixed"):
                conf = st.session_state.study_config

                async def do_handoff():
                    from api_client import APIClient
                    client = APIClient()
                    schema, table = (
                        conf["training_table"].split(".", 1)
                        if "." in conf["training_table"]
                        else ("clean_data", conf["training_table"])
                    )
                    return await client.export_handoff(source_table=table, source_schema=schema)

                try:
                    res = asyncio.run(do_handoff())
                    st.session_state.handoff_token = res
                    st.session_state.pending_mel_confirmation = False
                    _go("MEL")
                    st.rerun()
                except Exception as e:
                    st.error(f"Handoff failed: {e}")

            if st.button("Cancel", key="cancel_mel_btn"):
                st.session_state.pending_mel_confirmation = False
                st.rerun()

    if st.session_state.current_agent == "DIO":
        st.divider()
        from views.dio import render_dio_left_panel
        render_dio_left_panel()

# ── Right Panel: Dynamic Visual Canvas ────────────────────────────────────────
with right_col:
    agent = st.session_state.current_agent

    if agent == "Prepper":
        from views.prepper import render_prepper_view
        render_prepper_view()

    elif agent == "DIO":
        from views.dio import render_dio_view
        render_dio_view()

    elif agent == "MEL":
        from views.mel import render_mel_view
        render_mel_view()

    elif agent == "SIMO":
        from views.simo import render_simo_view
        render_simo_view()
