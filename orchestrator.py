"""
SLR Pipeline Orchestrator

Wires LM Studio → DIO → MEL → SIMO using MCP tool manifests via the
OpenAI function-calling SDK.

Usage:
    python orchestrator.py [--no-clean] [--levels 1 2 3 4 5]

The orchestrator fetches each agent's tool manifest from /tools, exposes
them to LM Studio as OpenAI functions, and routes tool calls to the
appropriate agent's /call/<tool_name> endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # read .env so LM_STUDIO_URL / PGHOST etc. are available

# ── Agent base URLs ───────────────────────────────────────────────────────────

DIO_URL  = os.getenv("DIO_URL",  "http://localhost:7001")
MEL_URL  = os.getenv("MEL_URL",  "http://localhost:7002")
SIMO_URL = os.getenv("SIMO_URL", "http://localhost:7003")

LM_STUDIO_URL   = os.getenv("LM_STUDIO_URL",   "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

_AGENT_ROUTING: Dict[str, str] = {}  # tool_name → base_url


# ── Tool discovery ────────────────────────────────────────────────────────────

async def fetch_tools(agent_url: str) -> List[Dict[str, Any]]:
    """Fetch the OpenAI-compatible tool manifest from an agent."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{agent_url}/tools")
        resp.raise_for_status()
        raw_tools = resp.json()

    openai_tools = []
    for t in raw_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


async def discover_all_tools() -> List[Dict[str, Any]]:
    """Fetch tools from DIO, MEL, and SIMO; build routing table."""
    all_tools: List[Dict[str, Any]] = []
    for agent_url, label in [(DIO_URL, "DIO"), (MEL_URL, "MEL"), (SIMO_URL, "SIMO")]:
        try:
            tools = await fetch_tools(agent_url)
            for t in tools:
                _AGENT_ROUTING[t["function"]["name"]] = agent_url
            all_tools.extend(tools)
            print(f"  ✓ {label}: {len(tools)} tools loaded")
        except Exception as exc:
            print(f"  ✗ {label} unreachable ({exc}) — skipping")
    return all_tools


# ── Tool dispatch ─────────────────────────────────────────────────────────────

async def dispatch_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """POST arguments to the correct agent's /call/<tool_name> endpoint."""
    base_url = _AGENT_ROUTING.get(tool_name)
    if base_url is None:
        return {"error": f"Unknown tool: {tool_name}"}

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/call/{tool_name}",
            json=arguments,
            headers={"Content-Type": "application/json"},
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


# ── Orchestration loop ────────────────────────────────────────────────────────

def run_pipeline(
    clean: bool = True,
    flood_levels: Optional[List[float]] = None,
) -> None:
    """
    Execute the full DIO → MEL → SIMO pipeline using LM Studio as the
    coordinating LLM.  Falls back to direct API calls if LM Studio is
    unavailable.
    """
    if flood_levels is None:
        flood_levels = [1.0, 2.0, 3.0, 4.0, 5.0]

    print("\n🌊 SLR Pipeline Orchestrator\n" + "─" * 40)
    all_tools = asyncio.run(discover_all_tools())

    if not all_tools:
        print("\n❌ No agent tools discovered. Are the agents running?")
        sys.exit(1)

    print(f"\n📦 Total tools available: {len(all_tools)}")

    # Try LM Studio; fall back to direct sequential execution
    try:
        llm = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
        llm.models.list()  # probe
        print(f"✓ LM Studio connected at {LM_STUDIO_URL}")
        _run_with_llm(llm, all_tools, flood_levels, clean)
    except Exception as exc:
        print(f"⚠ LM Studio unavailable ({exc}). Running direct sequential pipeline.")
        asyncio.run(_run_direct(flood_levels, clean))


def _run_with_llm(
    llm: OpenAI,
    tools: List[Dict[str, Any]],
    flood_levels: List[float],
    clean: bool,
) -> None:
    """Agentic loop: LM Studio calls tools until task is complete."""
    system_prompt = (
        "You are the SLR Pipeline orchestrator. "
        "Execute the following steps in order using the provided tools:\n"
        "1. DIO: Clean the NFIP claims data (clean_claims).\n"
        "2. DIO: Export a HandoffToken (export_handoff).\n"
        "3. MEL: Configure a training run using the HandoffToken (configure_run).\n"
        "4. MEL: Fit GMM on the target distribution (fit_gmm).\n"
        "5. MEL: Apply yeo-johnson transform (apply_transform).\n"
        "6. MEL: Train the ensemble models (train_ensemble).\n"
        "7. MEL: Select the best model (select_best).\n"
        "8. MEL: Export artifacts (export_artifacts).\n"
        "9. SIMO: Load the artifact (load_artifact).\n"
        f"10. SIMO: Run simulation for flood levels {flood_levels} (run_simulation).\n"
        "11. SIMO: Invalidate the tile cache (invalidate_tile_cache).\n"
        "Report the final simulation results when done."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Start the pipeline now."},
    ]

    print("\n🤖 Handing control to LM Studio…\n")

    max_iterations = 20
    for i in range(max_iterations):
        response = llm.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.0,
        )

        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_none=True))

        if choice.finish_reason == "stop":
            print("\n✅ Pipeline complete.")
            print(choice.message.content)
            break

        if choice.finish_reason == "tool_calls":
            for tc in choice.message.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                print(f"  → Calling {tool_name}({list(args.keys())})")
                result = asyncio.run(dispatch_tool(tool_name, args))
                print(f"    ← {str(result)[:120]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
    else:
        print("\n⚠ Max iterations reached — check agent logs.")


async def _run_direct(flood_levels: List[float], clean: bool) -> None:
    """Direct sequential pipeline without LLM orchestration."""
    print("\n▶ Step 1: DIO — Clean claims")
    r = await dispatch_tool("clean_claims", {"missing_strategy": "drop", "depth_unit": "inches"})
    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return
    print(f"  status={r.get('status')}  rows={r.get('rows_written')}")

    print("\n▶ Step 2: DIO — Export HandoffToken")
    handoff = await dispatch_tool("export_handoff", {})
    print(f"  Tables: {[t['name'] for t in handoff.get('tables', [])]}")

    print("\n▶ Step 3: MEL — Configure run")
    r = await dispatch_tool("configure_run", {"handoff_token": handoff})
    run_id = r.get("run_id", "?")
    print(f"  run_id={run_id}, features={r.get('feature_count', '?')}")

    print("\n▶ Step 4: MEL — Fit GMM")
    r = await dispatch_tool("fit_gmm", {"n_components": 3})
    aic, bic = r.get('aic'), r.get('bic')
    if isinstance(aic, (int, float)) and isinstance(bic, (int, float)):
        print(f"  AIC={aic:.1f}  BIC={bic:.1f}")
    else:
        print(f"  {r}")

    print("\n▶ Step 5: MEL — Apply transform")
    r = await dispatch_tool("apply_transform", {"method": "yeo-johnson"})
    print(f"  {r}")

    print("\n▶ Step 6: MEL — Train ensemble")
    r = await dispatch_tool("train_ensemble", {})
    for m in r.get("metrics", []):
        print(f"  {m['model_name']}: R2={m['R2']}")

    print("\n▶ Step 7: MEL — Select best")
    best = await dispatch_tool("select_best", {"metric": "R2"})
    print(f"  Best: {best.get('model_name')} R2={best.get('r2')}")

    print("\n▶ Step 8: MEL — Export artifacts")
    artifact_token = await dispatch_tool("export_artifacts", {})
    print(f"  Artifact dir: {artifact_token.get('artifact_dir')}")

    print("\n▶ Step 9: SIMO — Load artifact")
    r = await dispatch_tool("load_artifact", {"artifact_token": artifact_token})
    print(f"  {r}")

    print(f"\n▶ Step 10: SIMO — Run simulation for levels {flood_levels}")
    report = await dispatch_tool("run_simulation", {"flood_levels": flood_levels})
    for k, v in report.get("results_by_level", {}).items():
        print(f"  {k}: {v['parcel_count']} parcels, exposure=${v['total_exposure']:,.0f}")

    print("\n▶ Step 11: SIMO — Invalidate tile cache")
    r = await dispatch_tool("invalidate_tile_cache", {"levels": flood_levels})
    print(f"  {r}")

    print("\n✅ Pipeline complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SLR Pipeline Orchestrator")
    parser.add_argument("--no-clean", action="store_true", help="Skip DIO cleaning step")
    parser.add_argument("--levels", nargs="+", type=float, default=[1, 2, 3, 4, 5],
                        help="Flood levels (ft) to simulate")
    args = parser.parse_args()

    run_pipeline(
        clean=not args.no_clean,
        flood_levels=args.levels,
    )
