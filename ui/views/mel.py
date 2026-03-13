import streamlit as st
import asyncio
from api_client import APIClient
import plotly.express as px
import pandas as pd

def render_mel_view():
    st.header("🧠 Phase 2: Model Evaluation Lead (MEL)")
    st.markdown("Configure the model parameters and begin the training pipeline.")
    
    handoff_token = st.session_state.get("handoff_token")
    if not handoff_token:
        st.warning("No handoff token found. Please complete Phase 1 first.")
        return
        
    st.info(f"Handoff Token Received from DIO: {len(handoff_token.get('tables', []))} tables available.")
    
    col1, col2 = st.columns(2)
    with col1:
        target_col = st.selectbox(
            "Target Variable", 
            ["buildingdamageamount", "amountpaidonbuildingclaim"]
        )
    with col2:
        model_types = st.multiselect(
            "Ensemble Models to Train",
            ["Random Forest", "Gradient Boosting", "Hist Gradient Boosting"],
            default=["Random Forest", "Gradient Boosting", "Hist Gradient Boosting"]
        )
        
    if st.button("Train Ensemble Models"):
        with st.spinner("Training models in background container (this may take a minute)..."):
            async def train():
                client = APIClient()
                return await client.run_full_training_pipeline(handoff_token, target_col)
                
            try:
                res = asyncio.run(train())
                
                st.session_state.mel_metrics = res.get("metrics", [])
                st.session_state.artifact_token = res.get("artifact_token")
                
                st.success("Training complete! Best model selected and artifacts exported.")
            except Exception as e:
                st.error(f"Training failed: {e}")
                
    # If training is done and we have metrics, show Plotly dashboards
    if st.session_state.get("mel_metrics"):
        st.subheader("Model Evaluation Dashboard")
        
        metrics = st.session_state.mel_metrics
        df_metrics = pd.DataFrame(metrics)
        
        if not df_metrics.empty:
            st.markdown("### R² by Model")
            fig = px.bar(df_metrics, x="model_name", y="R2", color="model_name", text_auto=".3f",
                         title="R² Comparison (Averaged Over Ensemble)")
            fig.update_layout(yaxis_title="R² Score", xaxis_title="Model")
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### RMSE by Model")
            fig2 = px.bar(df_metrics, x="model_name", y="RMSE", color="model_name", text_auto=".0f",
                          title="Root Mean Squared Error")
            fig2.update_layout(yaxis_title="RMSE ($)", xaxis_title="Model")
            st.plotly_chart(fig2, use_container_width=True)
            
        else:
            st.info("Waiting for metric results...")
            
        if st.button("Deploy Best Model to SIMO"):
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Model deployed to artifact store. Transitioning to Phase 3 (SIMO) to view SLR scenarios!"
            })
            st.session_state.active_phase = 3
            st.rerun()
