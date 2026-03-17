import streamlit as st
import time

def render_agent_card(name, role, behaviors, knowledge):
    """Renders a professional system card for an agent."""
    with st.container():
        st.subheader(name, anchor=False)
        st.info(f"**Role**: {role}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Track 1: Behaviors")
            for b in behaviors:
                st.markdown(f"- {b}")
                
        with col2:
            st.markdown("### Track 2: Domain Knowledge")
            for k in knowledge:
                st.markdown(f"- {k}")
        
        st.divider()

def main():
    st.set_page_config(
        page_title="SLR Pipeline Orchestration",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Initialize session state for config
    if "config_ready" not in st.session_state:
        st.session_state.config_ready = False

    # --- Header ---
    st.title("SLR Pipeline: MCP Orchestration Hub", anchor=False)
    st.caption("Central Control Plane for Multi-Agent Sea Level Rise Analysis")
    st.divider()

    # --- Agent Tabs ---
    tabs = st.tabs([
        "Prepper Setup", 
        "DIO (Data Operator)", 
        "MEL (Model Evaluation)", 
        "SIMO (Impact Modeler)"
    ])

    with tabs[0]:
        col_info, col_form = st.columns([1, 1])
        with col_info:
            render_agent_card(
                name="Prepper Setup",
                role="Environment architect and dependency orchestrator.",
                behaviors=[
                    "Validates Docker environment and network connectivity.",
                    "Ensures .env variables match system requirements.",
                    "Primary constraint: Cannot modify existing database data directly."
                ],
                knowledge=[
                    "Docker Compose orchestration",
                    "Environment variable management",
                    "System health diagnostics"
                ]
            )
        
        with col_form:
            st.markdown("### Environment Configuration")
            with st.form("prepper_form"):
                db_url = st.text_input("PostgreSQL URI", 
                                     value=st.session_state.get("DATABASE_URL", ""),
                                     type="password", 
                                     placeholder="postgresql://user:pass@host:port/dbname")
                lm_base = st.text_input("LM Studio API Base", 
                                      value=st.session_state.get("LM_STUDIO_API_BASE", "http://localhost:1234/v1"),
                                      placeholder="http://localhost:1234/v1")
                
                submitted = st.form_submit_button("Verify & Save Configuration", use_container_width=True)
                
                if submitted:
                    with st.status("Verifying connections...", expanded=True) as status:
                        st.write("Checking database availability...")
                        time.sleep(1) # Mock check
                        st.write("Pinging LLM inference server...")
                        time.sleep(0.5) # Mock check
                        status.update(label="System Ready", state="complete", expanded=False)
                    
                    st.session_state.DATABASE_URL = db_url
                    st.session_state.LM_STUDIO_API_BASE = lm_base
                    st.session_state.config_ready = True
                    st.toast("Credentials stored in session state.", icon="✅")

    with tabs[1]:
        render_agent_card(
            name="DIO (Data Operator)",
            role="Specialist in data ingestion, cleaning, and schema management.",
            behaviors=[
                "Read-only access to raw source tables.",
                "Writes restricted to the clean_data schema.",
                "Constraint: Must log all data transformations for auditability."
            ],
            knowledge=[
                "PostgreSQL / PostGIS schema design",
                "Automated data cleaning pipelines",
                "MVT (Mapbox Vector Tile) generation"
            ]
        )

    with tabs[2]:
        render_agent_card(
            name="MEL (Model Evaluation)",
            role="Analytical engine for model training and metric validation.",
            behaviors=[
                "Trains ensemble models on cleaned historical claims.",
                "Evaluates performance using R², RMSE, and MAE.",
                "Constraint: Models must be exported to a versioned artifact store."
            ],
            knowledge=[
                "Random Forest & Gradient Boosting ensembles",
                "Yeo-Johnson & Power transformations",
                "Gaussian Mixture Modeling (GMM)"
            ]
        )

    with tabs[3]:
        render_agent_card(
            name="SIMO (Impact Modeler)",
            role="Simulation specialist for sea level rise and parcel-level risk.",
            behaviors=[
                "Applies MEL-trained models to large-scale parcel datasets.",
                "Calculates exposure and damage across multiple SLR scenarios.",
                "Constraint: RAG memory is limited to verified simulation results."
            ],
            knowledge=[
                "Parcel-level flood exposure modeling",
                "RAG-based simulation memory (ChromaDB)",
                "Risk aggregation by ZIP code and municipality"
            ]
        )

    # --- Launch Sequence ---
    st.write("")
    launch_col1, launch_col2, launch_col3 = st.columns([1, 2, 1])
    with launch_col2:
        if st.button("Launch SLR Simulation Environment", 
                     type="primary", 
                     icon="🚀",
                     use_container_width=True,
                     disabled=not st.session_state.config_ready):
            st.switch_page("pages/simulator.py")
        
        if not st.session_state.config_ready:
            st.caption("⚠️ Please verify environment settings in the **Prepper Setup** tab to enable launch.")

    # --- System Topography & Knowledge Graph ---
    st.write("")
    with st.expander("System Topography & Knowledge Graph", expanded=False):
        st.markdown("### Architectural Neural Connectivity")
        st.caption("Visualizing directional data handoffs and service dependencies.")
        
        import plotly.graph_objects as go

        # Nodes and their coordinates (manual layout for clarity)
        nodes = {
            "User/Researcher": (0, 1),
            "Prepper Agent": (1, 2),
            "DIO Agent": (2, 1),
            "MEL Agent": (3, 1),
            "SIMO Agent": (4, 1),
            "PostgreSQL": (1, 0),
            "LM Studio": (4, 2)
        }

        # Directional Edges: (Source, Target, Label)
        edges = [
            ("User/Researcher", "Prepper Agent", "Initializes"),
            ("Prepper Agent", "PostgreSQL", "Configures"),
            ("DIO Agent", "PostgreSQL", "Read/Write"),
            ("DIO Agent", "MEL Agent", "Data Handoff"),
            ("MEL Agent", "SIMO Agent", "Model Handoff"),
            ("SIMO Agent", "LM Studio", "Inference"),
        ]

        edge_x = []
        edge_y = []
        for start_node, end_node, label in edges:
            x0, y0 = nodes[start_node]
            x1, y1 = nodes[end_node]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=1.5, color='#20B2AA'),
            hoverinfo='none',
            mode='lines'
        )

        node_x = []
        node_y = []
        node_text = []
        for name, (x, y) in nodes.items():
            node_x.append(x)
            node_y.append(y)
            node_text.append(name)

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            text=node_text,
            textposition="top center",
            hoverinfo='text',
            marker=dict(
                size=25,
                color='#0A192F',
                line=dict(width=2, color='#20B2AA')
            )
        )

        fig = go.Figure(data=[edge_trace, node_trace],
                     layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=0, l=0, r=0, t=0),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        height=400
                    ))
        
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown("### Global Control Plane Settings")
        c1, c2 = st.columns(2)
        with c1:
            st.toggle("Enable Verbose MCP Logging", value=True, help="Stream detailed agent traces to the terminal.")
            st.toggle("Enable RAG Auto-Indexing", value=True, help="Automatically index simulation results into ChromaDB.")
        with c2:
            st.selectbox("Set LLM Inference Port", options=[1234, 8080, 11434], index=0)
            st.select_slider("Agent Concurrency Limit", options=[1, 2, 4, 8], value=4)

if __name__ == "__main__":
    main()
