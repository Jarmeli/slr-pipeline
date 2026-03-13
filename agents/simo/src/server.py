"""SIMO — Scenario & Inference MCP Server + Web UI."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shared.db import audit, close_pool, get_pool, write_audit
from shared.schemas import ArtifactToken, SimulationResult
from . import simulator as _sim
from . import rag as _rag

UI_DIR = Path(__file__).resolve().parent / "ui"

# Cached artifact token (set when run_simulation is called)
_artifact_token: Optional[ArtifactToken] = None
_last_report: Optional[Dict[str, Any]] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="SIMO — Scenario & Inference Model", version="1.0.0", lifespan=lifespan)

if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


# ── MCP tool manifest ─────────────────────────────────────────────────────────

@app.get("/tools")
async def list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "load_artifact",
            "description": "Load a model artifact from an ArtifactToken produced by MEL.",
            "parameters": {
                "type": "object",
                "properties": {"artifact_token": {"type": "object"}},
                "required": ["artifact_token"],
            },
        },
        {
            "name": "run_simulation",
            "description": "Run flood damage simulation for 1–5 ft levels across all parcels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flood_levels": {
                        "type": "array",
                        "items": {"type": "number"},
                        "default": [1, 2, 3, 4, 5],
                    },
                },
                "required": [],
            },
        },
        {
            "name": "get_report",
            "description": "Return JSON summary for a specific flood level.",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "number"}},
                "required": ["level"],
            },
        },
        {
            "name": "invalidate_tile_cache",
            "description": "Delete damage tile_cache rows so the Leaflet app fetches fresh tiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "levels": {"type": "array", "items": {"type": "number"}},
                },
                "required": [],
            },
        },
        {
            "name": "chat",
            "description": "Ask a natural-language question about simulation results (RAG).",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    ]


# ── Tool endpoints ────────────────────────────────────────────────────────────

@app.post("/call/load_artifact")
async def load_artifact_endpoint(request: Request) -> JSONResponse:
    global _artifact_token
    body = await request.json()
    token_data = body.get("artifact_token", {})
    _artifact_token = ArtifactToken(**token_data)
    return JSONResponse(content={"status": "ok", "run_id": _artifact_token.run_id, "model": _artifact_token.best_model_name})


@app.post("/call/run_simulation")
async def run_simulation_endpoint(request: Request) -> JSONResponse:
    global _last_report
    if _artifact_token is None:
        return JSONResponse(status_code=400, content={"error": "No artifact loaded. Call load_artifact first."})

    body = await request.json()
    flood_levels = body.get("flood_levels", [1, 2, 3, 4, 5])

    try:
        report = await _sim.run_simulation(
            artifact_dir=_artifact_token.artifact_dir,
            flood_levels=flood_levels,
            zip_dist_map=_artifact_token.zip_dist_map,
            one_hot_cols=_artifact_token.one_hot_cols,
            feature_cols=_artifact_token.feature_cols,
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    _last_report = report

    # Index into RAG
    try:
        _rag.index_simulation_report(report["run_id"], report)
    except Exception:
        pass  # RAG indexing failure is non-fatal

    asyncio.ensure_future(write_audit("SIMO", "run_simulation", {"flood_levels": flood_levels}, f"run_id={report.get('run_id')}", "success"))
    return JSONResponse(content=report)


@app.post("/call/get_report")
async def get_report_endpoint(request: Request) -> JSONResponse:
    if _last_report is None:
        return JSONResponse(status_code=400, content={"error": "No simulation run yet."})
    body = await request.json()
    level = float(body.get("level", 1))
    key = f"{int(level)}ft" if level == int(level) else f"{level}ft"
    stats = _last_report.get("results_by_level", {}).get(key)
    if stats is None:
        return JSONResponse(status_code=404, content={"error": f"No data for level {level}ft"})
    return JSONResponse(content=stats)


@app.post("/call/invalidate_tile_cache")
async def invalidate_cache_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    levels = body.get("levels", None)
    result = await _sim.invalidate_tile_cache(levels)
    return JSONResponse(content=result)


@app.post("/call/chat")
async def chat_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    question = body.get("question", "")
    if not question:
        return JSONResponse(status_code=400, content={"error": "question is required"})
    try:
        answer = _rag.chat(question)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return JSONResponse(content={"answer": answer})


# ── Convenience POST /chat (for the web UI) ───────────────────────────────────

@app.post("/chat")
async def chat_ui(request: Request) -> JSONResponse:
    return await chat_endpoint(request)


# ── Generic call router ───────────────────────────────────────────────────────

@app.post("/call/{tool_name}")
async def call_tool(tool_name: str, request: Request) -> JSONResponse:
    route_map = {
        "load_artifact": load_artifact_endpoint,
        "run_simulation": run_simulation_endpoint,
        "get_report": get_report_endpoint,
        "invalidate_tile_cache": invalidate_cache_endpoint,
        "chat": chat_endpoint,
    }
    handler = route_map.get(tool_name)
    if handler is None:
        return JSONResponse(status_code=404, content={"error": f"Tool '{tool_name}' not found"})
    return await handler(request)


# ── SIMO Web UI ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def simo_ui() -> HTMLResponse:
    return HTMLResponse(_SIMO_HTML)


_SIMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>SIMO — Scenario Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
    #header { padding: 0.75rem 1.25rem; background: rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }
    #header h1 { font-size: 1rem; font-weight: 700; color: #38bdf8; }
    #main { display: flex; flex: 1; overflow: hidden; }
    #map { flex: 1; }
    #sidebar {
      width: 340px; display: flex; flex-direction: column;
      background: rgba(15,17,23,0.96); border-left: 1px solid rgba(255,255,255,0.08);
      overflow: hidden; flex-shrink: 0;
    }
    #controls { padding: 1rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
    #controls h2 { font-size: 0.85rem; color: #38bdf8; margin-bottom: 0.75rem; font-weight: 600; }
    .field { margin-bottom: 0.6rem; }
    label { display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.2rem; }
    input[type="range"] { width: 100%; accent-color: #38bdf8; }
    .slider-val { font-size: 0.9rem; font-weight: 700; color: #38bdf8; margin-left: 0.5rem; }
    .btn { width: 100%; padding: 0.5rem; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 0.85rem; margin-top: 0.4rem; }
    .btn-primary { background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; }
    .btn-secondary { background: rgba(255,255,255,0.08); color: #e2e8f0; border: 1px solid rgba(255,255,255,0.15); }
    #stats { padding: 0.75rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
    .stat-row { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 0.25rem 0; }
    .stat-label { color: #94a3b8; }
    .stat-val { color: #e2e8f0; font-weight: 600; }
    #chat { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    #chatMessages { flex: 1; overflow-y: auto; padding: 0.75rem; font-size: 0.8rem; }
    .msg { margin-bottom: 0.6rem; line-height: 1.5; }
    .msg.user { color: #38bdf8; }
    .msg.assistant { color: #e2e8f0; }
    .msg.error { color: #f87171; }
    #chatInput { display: flex; gap: 0.5rem; padding: 0.6rem; border-top: 1px solid rgba(255,255,255,0.08); }
    #chatInput input { flex: 1; padding: 0.4rem 0.6rem; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; color: #e2e8f0; font-size: 0.8rem; outline: none; }
    #chatInput button { padding: 0.4rem 0.75rem; background: #0ea5e9; border: none; border-radius: 6px; color: #fff; cursor: pointer; font-size: 0.8rem; }
    #legend { position: absolute; bottom: 30px; left: 12px; z-index: 1000; background: rgba(15,17,23,0.88); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 0.6rem 0.85rem; font-size: 0.75rem; }
    #legend h3 { font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.35rem; }
    .legend-item { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.2rem; }
    .legend-swatch { width: 14px; height: 14px; border-radius: 3px; }
  </style>
</head>
<body>
  <div id="header">
    <span>🌊</span>
    <h1>SIMO — Flood Scenario Simulator</h1>
  </div>
  <div id="main">
    <div id="map"></div>
    <div id="sidebar">
      <div id="controls">
        <h2>Flood Scenario</h2>
        <div class="field">
          <label>Sea Level Rise: <span class="slider-val" id="levelVal">1 ft</span></label>
          <input type="range" id="levelSlider" min="1" max="5" step="1" value="1"/>
        </div>
        <button class="btn btn-primary" id="runBtn">▶ Run Simulation</button>
        <button class="btn btn-secondary" id="refreshBtn" style="margin-top:0.4rem">↻ Refresh Map</button>
      </div>
      <div id="stats">
        <div class="stat-row"><span class="stat-label">Flood Level</span><span class="stat-val" id="sLevel">—</span></div>
        <div class="stat-row"><span class="stat-label">Parcels Affected</span><span class="stat-val" id="sParcels">—</span></div>
        <div class="stat-row"><span class="stat-label">Total Exposure</span><span class="stat-val" id="sExposure">—</span></div>
        <div class="stat-row"><span class="stat-label">Mean Damage</span><span class="stat-val" id="sMean">—</span></div>
      </div>
      <div id="chat">
        <div id="chatMessages">
          <div class="msg assistant">💬 Ask me about flood damage predictions for this area.</div>
        </div>
        <div id="chatInput">
          <input type="text" id="chatQ" placeholder="Ask about the simulation…" />
          <button id="sendBtn">Send</button>
        </div>
      </div>
    </div>
  </div>
  <div id="legend">
    <h3>Predicted Damage</h3>
    <div class="legend-item"><div class="legend-swatch" style="background:#1e3a5f"></div><span>&lt; $10k</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background:#2563eb"></div><span>$10k – $50k</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background:#f59e0b"></div><span>$50k – $150k</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background:#dc2626"></div><span>&gt; $150k</span></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map').setView([25.88, -81.72], 12);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'ESRI World Imagery', maxZoom: 19
    }).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
      opacity: 0.5, maxZoom: 19
    }).addTo(map);

    let currentLevel = 1;
    const slider = document.getElementById('levelSlider');
    slider.addEventListener('input', () => {
      currentLevel = parseInt(slider.value);
      document.getElementById('levelVal').textContent = currentLevel + ' ft';
    });

    // Run simulation
    document.getElementById('runBtn').addEventListener('click', async () => {
      const btn = document.getElementById('runBtn');
      btn.disabled = true; btn.textContent = '⏳ Running…';
      try {
        const res = await fetch('/call/run_simulation', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ flood_levels: [1,2,3,4,5] })
        });
        const data = await res.json();
        if (res.ok) updateStats(data, currentLevel);
        else alert('Error: ' + (data.error || 'unknown'));
      } catch(e) { alert('Network error: ' + e.message); }
      btn.disabled = false; btn.textContent = '▶ Run Simulation';
    });

    let lastReport = null;
    slider.addEventListener('change', () => {
      if (lastReport) updateStats(lastReport, currentLevel);
    });

    function updateStats(report, level) {
      lastReport = report;
      const key = level + 'ft';
      const s = report.results_by_level?.[key];
      if (!s) return;
      document.getElementById('sLevel').textContent = level + ' ft';
      document.getElementById('sParcels').textContent = s.parcel_count?.toLocaleString() || '—';
      document.getElementById('sExposure').textContent = s.total_exposure ? '$' + Math.round(s.total_exposure).toLocaleString() : '—';
      document.getElementById('sMean').textContent = s.mean_damage ? '$' + Math.round(s.mean_damage).toLocaleString() : '—';
    }

    // Chat
    async function sendChat() {
      const input = document.getElementById('chatQ');
      const messages = document.getElementById('chatMessages');
      const q = input.value.trim();
      if (!q) return;
      input.value = '';
      messages.innerHTML += `<div class="msg user">You: ${q}</div>`;
      messages.scrollTop = messages.scrollHeight;
      try {
        const res = await fetch('/chat', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ question: q })
        });
        const data = await res.json();
        messages.innerHTML += `<div class="msg assistant">🤖 ${data.answer || data.error}</div>`;
      } catch(e) {
        messages.innerHTML += `<div class="msg error">Error: ${e.message}</div>`;
      }
      messages.scrollTop = messages.scrollHeight;
    }

    document.getElementById('sendBtn').addEventListener('click', sendChat);
    document.getElementById('chatQ').addEventListener('keypress', e => { if (e.key === 'Enter') sendChat(); });
  </script>
</body>
</html>
"""
