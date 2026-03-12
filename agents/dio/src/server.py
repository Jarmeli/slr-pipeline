"""DIO — MCP Server + Web UI (FastAPI)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shared.db import close_pool, get_pool
from . import tools as _tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="DIO — Data Ingestion & Operations", version="1.0.0", lifespan=lifespan)

UI_DIR = Path(__file__).resolve().parent / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


# ── MCP tool endpoints ────────────────────────────────────────────────────────

@app.get("/tools")
async def list_tools() -> List[Dict[str, Any]]:
    """MCP tool manifest."""
    return [
        {
            "name": "list_raw_tables",
            "description": "List all tables in the public schema.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "describe_table",
            "description": "Return column metadata and row count for a table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "schema": {"type": "string", "default": "public"},
                },
                "required": ["table"],
            },
        },
        {
            "name": "clip_to_bbox",
            "description": "Clip a spatial table to a bounding box and save to clean_data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":    {"type": "string"},
                    "west":     {"type": "number"},
                    "south":    {"type": "number"},
                    "east":     {"type": "number"},
                    "north":    {"type": "number"},
                    "geom_col": {"type": "string", "default": "geometry"},
                },
                "required": ["table", "west", "south", "east", "north"],
            },
        },
        {
            "name": "clean_claims",
            "description": "Clean NFIP claims and write to clean_data.claims_processed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "missing_strategy": {"type": "string", "enum": ["drop", "mean"], "default": "drop"},
                    "depth_unit":       {"type": "string", "enum": ["inches", "feet"], "default": "inches"},
                },
                "required": [],
            },
        },
        {
            "name": "eda_summary",
            "description": "Return EDA statistics for numeric columns of a clean_data table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":  {"type": "string"},
                    "schema": {"type": "string", "default": "clean_data"},
                },
                "required": ["table"],
            },
        },
        {
            "name": "export_handoff",
            "description": "Build a HandoffToken for MEL containing clean_data table info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_col":   {"type": "string", "default": "buildingdamageamount"},
                    "feature_cols": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
        },
    ]


@app.post("/call/{tool_name}")
async def call_tool(tool_name: str, request: Request) -> JSONResponse:
    """Generic MCP tool-call endpoint."""
    body: Dict[str, Any] = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}

    fn = getattr(_tools, tool_name, None)
    if fn is None:
        return JSONResponse(status_code=404, content={"error": f"Tool '{tool_name}' not found"})

    try:
        result = await fn(**body)
        return JSONResponse(content={"result": result})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ── Convenience REST endpoints ────────────────────────────────────────────────

@app.get("/tables")
async def tables() -> JSONResponse:
    result = await _tools.list_raw_tables()
    return JSONResponse(content=result)


@app.post("/clip")
async def clip(request: Request) -> JSONResponse:
    body = await request.json()
    result = await _tools.clip_to_bbox(**body)
    return JSONResponse(content=result)


@app.post("/clean-claims")
async def clean_claims_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    result = await _tools.clean_claims(**body)
    return JSONResponse(content=result)


@app.get("/handoff")
async def handoff() -> JSONResponse:
    result = await _tools.export_handoff()
    return JSONResponse(content=result)


# ── Leaflet clipping map UI ───────────────────────────────────────────────────

@app.get("/map", response_class=HTMLResponse)
async def map_ui() -> HTMLResponse:
    return HTMLResponse(_MAP_HTML)


_MAP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>DIO — Spatial Clip Tool</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    body { margin:0; font-family: system-ui, sans-serif; background:#0f1117; color:#e2e8f0; }
    #header { padding:1rem 1.5rem; background:rgba(255,255,255,0.05); border-bottom:1px solid rgba(255,255,255,0.1); display:flex; align-items:center; gap:1rem; }
    #header h1 { font-size:1.1rem; font-weight:700; color:#38bdf8; margin:0; }
    #map { height: calc(100vh - 60px); }
    #panel {
      position: absolute; top: 80px; right: 16px; z-index: 1000;
      background: rgba(15,17,23,0.92); backdrop-filter:blur(8px);
      border: 1px solid rgba(255,255,255,0.12); border-radius:12px;
      padding: 1rem; width: 260px; font-size:0.85rem;
    }
    #panel h2 { font-size:0.9rem; color:#38bdf8; margin:0 0 0.75rem; }
    .field { margin-bottom:0.6rem; }
    label { display:block; color:#94a3b8; margin-bottom:0.2rem; font-size:0.78rem; }
    select, input { width:100%; padding:0.4rem 0.6rem; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15); border-radius:6px; color:#e2e8f0; font-size:0.82rem; }
    button { width:100%; padding:0.55rem; background:linear-gradient(135deg,#0ea5e9,#6366f1); border:none; border-radius:8px; color:#fff; font-weight:600; cursor:pointer; margin-top:0.5rem; }
    button:disabled { opacity:0.5; cursor:not-allowed; }
    #result { margin-top:0.75rem; padding:0.5rem; background:rgba(16,185,129,0.1); border:1px solid #10b981; border-radius:6px; color:#6ee7b7; display:none; font-size:0.8rem; }
    #coords { font-size:0.75rem; color:#64748b; margin-top:0.5rem; word-break:break-all; }
  </style>
</head>
<body>
  <div id="header">
    <span>📊</span><h1>DIO — Spatial Clip Tool</h1>
  </div>
  <div id="map"></div>
  <div id="panel">
    <h2>Clip to Bounding Box</h2>
    <div class="field">
      <label>Table</label>
      <select id="tableSelect"><option value="parcels_cliplayer">parcels_cliplayer</option></select>
    </div>
    <div id="coords">Draw a rectangle on the map to set bbox.</div>
    <button id="clipBtn" disabled>✂️ Clip & Save</button>
    <div id="result"></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map').setView([25.88, -81.72], 11);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'ESRI World Imagery', maxZoom: 19
    }).addTo(map);

    let rect = null, bbox = null;
    map.on('mousedown', startDraw);

    function startDraw(e) {
      if (!e.originalEvent.shiftKey) return;
      const start = e.latlng;
      map.dragging.disable();
      map.on('mousemove', onMove);
      map.on('mouseup', endDraw);

      function onMove(e2) {
        if (rect) map.removeLayer(rect);
        rect = L.rectangle([start, e2.latlng], {color:'#38bdf8', weight:2, fillOpacity:0.15}).addTo(map);
      }
      function endDraw(e2) {
        map.dragging.enable();
        map.off('mousemove', onMove);
        map.off('mouseup', endDraw);
        if (rect) {
          const b = rect.getBounds();
          bbox = {west:b.getWest(), south:b.getSouth(), east:b.getEast(), north:b.getNorth()};
          document.getElementById('coords').textContent =
            `W:${bbox.west.toFixed(4)} S:${bbox.south.toFixed(4)} E:${bbox.east.toFixed(4)} N:${bbox.north.toFixed(4)}`;
          document.getElementById('clipBtn').disabled = false;
        }
      }
    }

    document.getElementById('clipBtn').addEventListener('click', async () => {
      const btn = document.getElementById('clipBtn');
      const result = document.getElementById('result');
      const table = document.getElementById('tableSelect').value;
      btn.disabled = true;
      btn.textContent = '⏳ Clipping…';
      const res = await fetch('/clip', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({table, ...bbox})
      });
      const data = await res.json();
      result.style.display = 'block';
      result.textContent = res.ok
        ? `✅ ${data.rows_inserted} rows → ${data.destination}`
        : `❌ ${data.error}`;
      btn.disabled = false;
      btn.textContent = '✂️ Clip & Save';
    });

    // Load available tables
    fetch('/tables').then(r=>r.json()).then(tables => {
      const sel = document.getElementById('tableSelect');
      sel.innerHTML = tables.map(t=>`<option value="${t.table_name}">${t.table_name}</option>`).join('');
    });
  </script>
</body>
</html>
"""
