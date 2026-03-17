import asyncio

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from api_client import APIClient


def render_dio_view():
    st.header("Phase 1: Data Inventory Operator (DIO)", anchor=False)
    st.markdown("Use the drawing tools to define the bounds of the study area.")

    m = folium.Map(location=[26.13, -81.79], zoom_start=10)

    # Auto-fit bounds if extent is known from chat
    if st.session_state.get("map_extent"):
        m.fit_bounds(st.session_state.map_extent)

    Draw(
        export=True,
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
    ).add_to(m)

    # Persist the map output in session state so it survives navigation away and back
    output = st_folium(m, width=800, height=500, returned_objects=["last_active_drawing"],
                       key="dio_map")

    if st.button("Clip and Clean Data", type="primary"):
        if output and output.get("last_active_drawing"):
            drawing_geojson = output["last_active_drawing"]
            st.session_state.study_area_geojson = drawing_geojson

            with st.status("Processing study area...", expanded=True) as status:
                st.write("Sending geometry to DIO agent...")

                async def process_dio():
                    client = APIClient()
                    return await client.clip_study_area(drawing_geojson)

                try:
                    result = asyncio.run(process_dio())
                    st.write("Cleaning NFIP claims data...")
                    st.write("Writing clean_data.claims_processed...")
                    st.session_state.handoff_token = result.get("handoff_token", {})
                    status.update(label="Data clipped and cleaned.", state="complete", expanded=False)

                    st.toast("Data clipped and cleaned successfully.")
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"DIO prepared the structural inventory. {result.get('rows', '')} rows processed. Proceeding to MEL.",
                    })
                    st.session_state.unlocked_agents.add("MEL")
                    st.session_state.current_agent = "MEL"
                    st.session_state.active_phase = 2
                    st.rerun()

                except Exception as e:
                    status.update(label="Processing failed.", state="error", expanded=False)
                    st.error(f"DIO API error: {e}")
        else:
            st.warning("Please draw a polygon or rectangle on the map first.")


def render_dio_left_panel():
    st.markdown("### Existing Datasets")
    st.caption("Bypass spatial clipping and promote a pre-processed dataset directly to MEL.")

    @st.cache_data(ttl=60)
    def get_db_tables():
        client = APIClient()
        return asyncio.run(client.get_raw_tables())

    try:
        tables = get_db_tables()
        table_opts = [f"{t['table_schema']}.{t['table_name']}" for t in tables]
    except Exception:
        table_opts = []

    selected_tbl = st.selectbox("Select dataset for modeling:", table_opts)

    if st.button("Use Selected Dataset", use_container_width=True):
        if not selected_tbl:
            st.warning("No table selected.")
            return

        schema, tname = selected_tbl.split(".", 1)

        with st.status(f"Fetching handoff token for {selected_tbl}...", expanded=False) as status:
            async def process_full():
                client = APIClient()
                return await client.export_handoff(source_table=tname, source_schema=schema)

            try:
                result = asyncio.run(process_full())
                st.session_state.handoff_token = result
                status.update(label="Handoff token received.", state="complete")

                st.toast(f"Using dataset {selected_tbl}.")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Skipped spatial clipping. Using dataset **{selected_tbl}**. Transitioning to MEL.",
                })
                st.session_state.unlocked_agents.add("MEL")
                st.session_state.current_agent = "MEL"
                st.session_state.active_phase = 2
                st.rerun()

            except Exception as e:
                status.update(label="Failed.", state="error")
                st.error(f"DIO handoff error: {e}")
