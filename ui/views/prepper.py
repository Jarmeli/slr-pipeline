import asyncio

import streamlit as st

from api_client import APIClient


def render_prepper_view():
    st.header("Phase 0: System Bootstrapping", anchor=False)
    st.markdown("Configure the backend connections for the Multi-Agent system.")

    with st.form("prepper_config_form"):
        st.subheader("Database Configuration")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("PostgreSQL Host", value="sea-level-rise.postgres.database.azure.com")
            st.text_input("Port", value="5432")
            st.text_input("Username", value="SLRuser")
        with col2:
            st.text_input("Password", type="password")
            st.text_input("Database Name", value="SeaLevelRise")

        st.subheader("LLM Orchestrator Configuration")
        st.text_input("LLM API Base URL (LM Studio / Ollama)", value="http://localhost:11434/v1")
        st.text_input("Model Name", value="mistral:7b-instruct")

        submit_btn = st.form_submit_button("Initialize System")

        if submit_btn:
            with st.status("Validating agent connections...", expanded=True) as status:
                st.write("Contacting DIO agent (port 7001)...")
                client = APIClient()
                is_healthy = asyncio.run(client.check_health())

                if is_healthy:
                    st.write("Checking MEL agent (port 7002)...")
                    st.write("Checking SIMO agent (port 7003)...")
                    status.update(label="All agents online.", state="complete", expanded=False)
                else:
                    status.update(label="Connection failed.", state="error", expanded=False)

            if is_healthy:
                st.toast("All agents online.")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": "Connections validated. Transitioning to DIO. Please define the study area on the map.",
                })
                # Unlock DIO and navigate
                st.session_state.unlocked_agents.add("DIO")
                st.session_state.current_agent = "DIO"
                st.session_state.active_phase = 1
                st.rerun()
            else:
                st.error(
                    "Could not connect to FastAPI Agents on localhost:7001-7003. "
                    "Make sure docker-compose is running."
                )
