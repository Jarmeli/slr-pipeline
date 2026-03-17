import asyncio

import pydeck as pdk
import streamlit as st
import folium
import pandas as pd
import plotly.express as px
from folium.plugins import Draw
from streamlit_folium import st_folium

from api_client import APIClient

# NOAA SLR public tile template (integer flood levels 1–10 ft)
_NOAA_TILE_TPL = (
    "https://coast.noaa.gov/slrdata/tiles/slr_{level}ft/{{z}}/{{x}}/{{y}}.png"
)


def _build_deck(flood_depth: float, show_parcels: bool, show_inundation: bool) -> pdk.Deck:
    """Construct a PyDeck Deck with optional raster + MVT layers."""
    layers = []

    if show_inundation:
        level_int = max(1, min(10, int(flood_depth)))
        layers.append(
            pdk.Layer(
                "TileLayer",
                data=_NOAA_TILE_TPL.format(level=level_int),
                min_zoom=0,
                max_zoom=19,
                tile_size=256,
                opacity=0.45,
                id="inundation_raster",
            )
        )

    if show_parcels:
        tile_url = (
            f"http://localhost:7003/tiles/parcel_damage/{{z}}/{{x}}/{{y}}.pbf"
            f"?flood_level={float(flood_depth)}"
        )
        layers.append(
            pdk.Layer(
                "MVTLayer",
                data=tile_url,
                get_fill_color=(
                    "[predicted_damage > 150000 ? 220 : predicted_damage > 50000 ? 245 : predicted_damage > 10000 ? 37 : 30,"
                    " predicted_damage > 150000 ? 38  : predicted_damage > 50000 ? 158 : predicted_damage > 10000 ? 99 : 58,"
                    " predicted_damage > 150000 ? 38  : predicted_damage > 50000 ? 11  : predicted_damage > 10000 ? 235 : 95,"
                    " 210]"
                ),
                get_line_color=[255, 255, 255, 80],
                line_width_min_pixels=1,
                pickable=True,
                id="parcel_damage_mvt",
            )
        )

    view_state = pdk.ViewState(latitude=26.13, longitude=-81.79, zoom=13, pitch=0)

    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=pdk.map_styles.DARK,
        tooltip={
            "html": (
                "<b>Parcel ID:</b> {parcel_id}<br/>"
                "<b>Elevation:</b> {elevation} ft<br/>"
                "<b>Predicted Damage:</b> ${predicted_damage}"
            ),
            "style": {"color": "white"},
        },
    )


def _render_legend(show_parcels: bool, show_inundation: bool) -> None:
    items = []
    if show_inundation:
        items += [
            "<b style='color:#94a3b8;font-size:0.72rem'>INUNDATION DEPTH</b>",
            "<div style='display:flex;align-items:center;gap:6px;margin:3px 0'>"
            "<div style='width:12px;height:12px;border-radius:3px;"
            "background:linear-gradient(to right,#bfdbfe,#1d4ed8)'></div>"
            "<span>Shallow to Deep</span></div>",
        ]
    if show_parcels:
        items += [
            "<b style='color:#94a3b8;font-size:0.72rem;margin-top:6px;display:block'>PREDICTED DAMAGE</b>",
            "<div style='display:flex;align-items:center;gap:6px;margin:3px 0'><div style='width:12px;height:12px;border-radius:3px;background:#1e3a5f'></div><span>&lt; $10k</span></div>",
            "<div style='display:flex;align-items:center;gap:6px;margin:3px 0'><div style='width:12px;height:12px;border-radius:3px;background:#2563eb'></div><span>$10k to $50k</span></div>",
            "<div style='display:flex;align-items:center;gap:6px;margin:3px 0'><div style='width:12px;height:12px;border-radius:3px;background:#f59e0b'></div><span>$50k to $150k</span></div>",
            "<div style='display:flex;align-items:center;gap:6px;margin:3px 0'><div style='width:12px;height:12px;border-radius:3px;background:#dc2626'></div><span>&gt; $150k</span></div>",
        ]
    if items:
        st.markdown(
            "<div style='background:rgba(15,17,23,0.82);border:1px solid rgba(255,255,255,0.1);"
            "border-radius:8px;padding:10px 14px;font-size:0.8rem;color:#e2e8f0'>"
            + "".join(items)
            + "</div>",
            unsafe_allow_html=True,
        )


def render_simo_view():
    st.header("Phase 3: Scenario Impact Modeler (SIMO)", anchor=False)

    artifact_token = st.session_state.get("artifact_token")
    if not artifact_token:
        st.warning("No artifact token found. Please complete Phase 2 (MEL) first.")
        return

    # Scenario Control
    st.sidebar.subheader("Scenario Controls")
    flood_depth = st.sidebar.slider(
        "Sea Level Rise (ft)", min_value=1.0, max_value=5.0, value=3.0, step=1.0
    )

    if st.button("Run Simulation Scenario", type="primary"):
        with st.status("Running flood simulation...", expanded=True) as status:
            st.write("Loading model artifact...")
            st.write("Scoring parcels against real elevation and zip data...")
            st.write("Writing results to parcel_damage table...")
            st.write("Indexing simulation report into RAG knowledge base...")

            async def run_sim():
                client = APIClient()
                await client.load_artifact(artifact_token)
                overrides = st.session_state.get("parcel_value_override", {})
                config = st.session_state.get("study_config", {})
                return await client.run_simulation(
                    flood_levels=[float(flood_depth)],
                    value_table=overrides.get("table") or config.get("values_table"),
                    value_col=overrides.get("column") or config.get("values_col"),
                    parcel_table=config.get("prediction_table", "public.parcels_cliplayer"),
                )

            try:
                res = asyncio.run(run_sim())
                st.session_state.simulation_results = res
                status.update(label="Simulation complete.", state="complete", expanded=False)
                st.toast("Simulation complete. Results written to PostGIS.")
            except Exception as e:
                status.update(label="Simulation failed.", state="error", expanded=False)
                st.error(f"Simulation failed: {e}")

    # KPI Metrics
    sim_res = st.session_state.get("simulation_results")
    if sim_res and sim_res.get("results_by_level"):
        lvl_key = f"{float(flood_depth)}ft"
        lvl_data = sim_res["results_by_level"].get(lvl_key, {})
        if lvl_data:
            st.subheader("Regional Impact Summary", anchor=False)
            m1, m2, m3 = st.columns(3)
            with m1:
                total_exp = lvl_data.get("total_exposure", 0) / 1e9
                st.metric("Total Predicted Damage", f"${total_exp:.2f} B")
            with m2:
                mean_dmg = lvl_data.get("mean_damage", 0)
                st.metric("Mean Damage / Parcel", f"${mean_dmg:,.0f}")
            with m3:
                count = lvl_data.get("parcel_count", 0)
                st.metric("Parcels Scored", f"{count:,}")

    # Map Tabs
    tab1, tab2 = st.tabs(
        ["County-wide View", "Regional Assessment"]
    )

    with tab1:
        st.subheader("Interactive Inundation Map", anchor=False)

        lc, rc = st.columns(2)
        with lc:
            show_parcels = st.checkbox("Show Parcel Damage", value=True, key="chk_parcels")
        with rc:
            show_inundation = st.checkbox(
                "Show Inundation Depth (NOAA)", value=True, key="chk_inundation"
            )

        deck = _build_deck(flood_depth, show_parcels, show_inundation)
        st.pydeck_chart(deck)
        _render_legend(show_parcels, show_inundation)

    with tab2:
        st.subheader("Regional Selection", anchor=False)
        st.write("Draw a polygon to assess localized damage metrics for a specific neighborhood.")

        m = folium.Map(location=[26.13, -81.79], zoom_start=13)
        Draw(
            export=True,
            draw_options={
                "polyline": False, "circle": False,
                "marker": False, "circlemarker": False,
            },
        ).add_to(m)

        output = st_folium(m, width=800, height=500, key="simo_draw")

        if output and output.get("last_active_drawing"):
            poly = output["last_active_drawing"].get("geometry")
            if poly:
                with st.status("Calculating regional statistics...", expanded=False) as status:
                    async def fetch_stats():
                        client = APIClient()
                        return await client.get_regional_stats(poly, float(flood_depth))

                    try:
                        stats = asyncio.run(fetch_stats())
                        status.update(label="Done.", state="complete")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("Parcels in Selection", f"{stats['parcel_count']:,}")
                        with c2:
                            st.metric("Total Regional Exposure", f"${stats['total_exposure']:,.0f}")
                        with c3:
                            st.metric("Avg Damage / Parcel", f"${stats['mean_damage']:,.0f}")
                    except Exception as e:
                        status.update(label="Failed.", state="error")
                        st.error(f"Regional stats error: {e}")

    # --- Floating SLR Assistant (Popup) ---
    with st.sidebar:
        st.divider()
        with st.popover("💬 SLR Assistant", use_container_width=True):
            st.subheader("SLR Assistant", anchor=False)
            st.caption(
                "Ask questions across all agents: "
                "DIO (data), MEL (models), SIMO (flood impact)."
            )

            if "simo_canvas_chat" not in st.session_state:
                st.session_state.simo_canvas_chat = [
                    {
                        "role": "assistant",
                        "content": "I am your SLR Pipeline assistant. How can I help you today?",
                    }
                ]

            # Chat container for scrollability in popover
            chat_container = st.container(height=400)
            with chat_container:
                for msg in st.session_state.simo_canvas_chat:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            if q := st.chat_input("Ask about data, models...", key="simo_popover_input"):
                st.session_state.simo_canvas_chat.append({"role": "user", "content": q})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(q)

                # Intent routing logic
                q_lower = q.lower()
                _DIO_KW  = {"table", "schema", "tables", "dataset", "data", "column", "rows", "claims"}
                _MEL_KW  = {"model", "r2", "r²", "rmse", "mae", "accuracy", "training", "feature"}
                _SIMO_KW = {"flood", "damage", "parcel", "exposure", "simulation", "scenario"}

                words = set(q_lower.split())
                dio_score  = len(words & _DIO_KW)
                mel_score  = len(words & _MEL_KW)
                simo_score = len(words & _SIMO_KW)

                if dio_score >= mel_score and dio_score >= simo_score and dio_score > 0:
                    route = "DIO"
                elif mel_score >= simo_score and mel_score > 0:
                    route = "MEL"
                else:
                    route = "SIMO"

                with chat_container:
                    with st.chat_message("assistant"):
                        with st.spinner(f"Routing to {route}..."):
                            answer = ""
                            if route == "DIO":
                                try:
                                    tables = asyncio.run(APIClient().get_raw_tables())
                                    lines = [f"- `{t['table_schema']}.{t['table_name']}`" for t in tables]
                                    answer = "**DIO — Tables available:**\n\n" + "\n".join(lines)
                                except Exception as e:
                                    answer = f"Error reaching DIO: {e}"
                            elif route == "MEL":
                                metrics = st.session_state.get("mel_metrics", [])
                                if metrics:
                                    lines = [f"- **{m.get('model_name', '?')}** — R² `{m.get('R2', 0):.4f}`" for m in metrics]
                                    answer = "**MEL — Results:**\n\n" + "\n".join(lines)
                                else:
                                    answer = "No training results yet."
                            else:
                                try:
                                    rag_res = asyncio.run(APIClient().simo_chat(q))
                                    answer = rag_res.get("answer", "No answer found.")
                                except Exception as e:
                                    answer = f"**SIMO Assistant Error**: {e}\n\n*Check if SIMO container is running and ChromaDB is healthy.*"
                        
                        st.markdown(answer)
                        st.session_state.simo_canvas_chat.append({"role": "assistant", "content": answer})
                        st.rerun()

    # SIMO Report Logic (Embedded in Sidebar or separate tab)
    # The Executive Simulation Report is now handled in a collapsible popover or below.
    # To keep the UI clean, we can put the report summary in tab2 or below maps.



