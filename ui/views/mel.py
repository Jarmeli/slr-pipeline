import asyncio

import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import APIClient


def render_mel_view():
    st.header("Phase 2: Model Evaluation Lead (MEL)", anchor=False)
    st.markdown("Configure model parameters and run the training pipeline.")

    handoff_token = st.session_state.get("handoff_token")
    if not handoff_token:
        st.warning("No handoff token found. Please complete Phase 1 (DIO) first.")
        return

    n_tables = len(handoff_token.get("tables", []))
    st.info(f"Handoff token received from DIO — {n_tables} table(s) available.")

    col1, col2 = st.columns(2)
    with col1:
        target_col = st.selectbox(
            "Target Variable",
            ["buildingdamageamount", "amountpaidonbuildingclaim"],
        )
    with col2:
        st.multiselect(
            "Ensemble Models to Train",
            ["Random Forest", "Gradient Boosting", "Hist Gradient Boosting"],
            default=["Random Forest", "Gradient Boosting", "Hist Gradient Boosting"],
        )

    # ── EDA-First: load distributions on first render ─────────────────────────
    if "mel_distributions" not in st.session_state or st.session_state.mel_distributions is None:
        with st.spinner("Analyzing data distributions..."):
            async def init_eda():
                client = APIClient()
                return await client.configure_run(handoff_token, target_col)

            try:
                res = asyncio.run(init_eda())
                st.session_state.mel_distributions = res.get("distributions", {})
                st.session_state.mel_predictors = res.get("feature_cols", [])
            except Exception as e:
                st.error(f"Failed to load EDA: {e}")

    # ── EDA Charts ────────────────────────────────────────────────────────────
    st.subheader("Exploratory Data Analysis", anchor=False)
    dists = st.session_state.get("mel_distributions") or {}
    if dists:
        d_col1, d_col2 = st.columns(2)
        if dists.get("target"):
            with d_col1:
                fig_tgt = px.histogram(
                    x=dists["target"], nbins=50,
                    title=f"Distribution: {target_col}",
                    color_discrete_sequence=["#20B2AA"],
                )
                fig_tgt.update_layout(xaxis_title="Damage Amount ($)", yaxis_title="Count")
                st.plotly_chart(fig_tgt, use_container_width=True)
        if dists.get("property_value"):
            with d_col2:
                fig_prop = px.histogram(
                    x=dists["property_value"], nbins=50,
                    title="Distribution: property_value",
                    color_discrete_sequence=["#0A9396"],
                )
                fig_prop.update_layout(xaxis_title="Property Value ($)", yaxis_title="Count")
                st.plotly_chart(fig_prop, use_container_width=True)

    preds = st.session_state.get("mel_predictors", [])
    if preds:
        with st.expander("View Model Predictors (Feature Set)"):
            st.write(", ".join([f"`{p}`" for p in preds]))

    st.divider()

    # ── Training Gate ─────────────────────────────────────────────────────────
    st.subheader("Model Training", anchor=False)
    eda_reviewed = st.checkbox(
        "I have reviewed the data distributions and predictors.", value=False
    )

    if st.button("Train Ensemble Models", disabled=not eda_reviewed, type="primary"):
        with st.status("Running training pipeline...", expanded=True) as status:
            st.write("Configuring run...")
            st.write("Fitting Gaussian Mixture Model...")
            st.write("Applying Yeo-Johnson transform...")
            st.write("Training ensemble (Random Forest, Gradient Boosting, HGB)...")
            st.write("Selecting best model by R²...")
            st.write("Exporting model artifacts...")

            async def train():
                client = APIClient()
                return await client.run_full_training_pipeline(handoff_token, target_col)

            try:
                res = asyncio.run(train())
                st.session_state.mel_metrics = res.get("metrics", [])
                st.session_state.artifact_token = res.get("artifact_token")
                status.update(label="Training complete. Best model exported.", state="complete", expanded=False)
                st.toast("Training complete. Best model exported.")
            except Exception as e:
                status.update(label="Training failed.", state="error", expanded=False)
                st.error(f"Training failed: {e}")

    # ── Metrics Table & Charts ────────────────────────────────────────────────
    metrics = st.session_state.get("mel_metrics", [])
    if metrics:
        df_metrics = pd.DataFrame(metrics)

        st.subheader("Model Performance", anchor=False)

        # Polished dataframe with column config
        if not df_metrics.empty:
            st.dataframe(
                df_metrics,
                use_container_width=True,
                column_config={
                    "model_name": st.column_config.TextColumn("Model"),
                    "R2":   st.column_config.NumberColumn("R²",       format="%.4f"),
                    "RMSE": st.column_config.NumberColumn("RMSE ($)", format="$%,.0f"),
                    "MAE":  st.column_config.NumberColumn("MAE ($)",  format="$%,.0f"),
                },
                hide_index=True,
            )

            fig = px.bar(
                df_metrics, x="model_name", y="R2", color="model_name",
                text_auto=".3f", title="R² Comparison",
                color_discrete_sequence=["#20B2AA", "#0A9396", "#005F73"],
            )
            fig.update_layout(yaxis_title="R² Score", xaxis_title="Model", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            fig2 = px.bar(
                df_metrics, x="model_name", y="RMSE", color="model_name",
                text_auto=".0f", title="Root Mean Squared Error",
                color_discrete_sequence=["#20B2AA", "#0A9396", "#005F73"],
            )
            fig2.update_layout(yaxis_title="RMSE ($)", xaxis_title="Model", showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

    # ── Contextual hand-off button (shown once artifact is ready) ─────────────
    if st.session_state.get("artifact_token"):
        st.divider()
        if st.button("Proceed to Simulation", type="primary"):
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Model artifacts exported. Transitioning to SIMO for flood scenario analysis.",
            })
            st.session_state.unlocked_agents.add("SIMO")
            st.session_state.current_agent = "SIMO"
            st.session_state.active_phase = 3
            st.rerun()
