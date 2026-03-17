import streamlit as st

st.set_page_config(page_title="SLR Simulator Workspace", layout="wide")

st.title("SLR Simulation & Intelligence Workspace")
st.caption("Active Session Transitioned from Orchestration Hub")

st.divider()

col1, col2 = st.columns([2, 1])

with col1:
    st.info("### Simulation Canvas")
    st.markdown("Map and Damage Analysis modules would load here, utilizing the state established in the Management UI.")
    
with col2:
    st.success("### Agent Connectivity")
    st.write(f"**Database**: `{st.session_state.get('DATABASE_URL', 'Not Configured')}`")
    st.write(f"**LM Studio**: `{st.session_state.get('LM_STUDIO_API_BASE', 'Not Configured')}`")

st.divider()

if st.button("Return to Orchestration Hub", icon="⚙️"):
    st.switch_page("app.py")
