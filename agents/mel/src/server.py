"""MEL — Model Ensemble Learner MCP Server."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sklearn.model_selection import train_test_split

from shared.db import audit, close_pool, get_pool, write_audit
from shared.schemas import ArtifactToken, HandoffToken, ModelMetrics
from . import trainer as _trainer
from . import evaluator as _evaluator

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/artifacts"))

# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="MEL — Model Ensemble Learner", version="1.0.0", lifespan=lifespan)

# In-memory run state (single-process; fine for this use case)
_run_state: Dict[str, Any] = {}


# ── MCP tool manifest ─────────────────────────────────────────────────────────

@app.get("/tools")
async def list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "configure_run",
            "description": "Accept a HandoffToken from DIO and configure the training run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "handoff_token": {"type": "object"},
                    "target_col": {"type": "string", "default": "buildingdamageamount"},
                    "test_size": {"type": "number", "default": 0.2},
                    "random_state": {"type": "integer", "default": 42},
                },
                "required": ["handoff_token"],
            },
        },
        {
            "name": "apply_transform",
            "description": "Apply a power transform to the training target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["yeo-johnson", "box-cox", "log"], "default": "yeo-johnson"},
                },
                "required": [],
            },
        },
        {
            "name": "fit_gmm",
            "description": "Fit a Gaussian Mixture Model on the target to understand its distribution.",
            "parameters": {
                "type": "object",
                "properties": {"n_components": {"type": "integer", "default": 3}},
                "required": [],
            },
        },
        {
            "name": "train_ensemble",
            "description": "Train ensemble regressors and return comparison metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "models": {"type": "array", "items": {"type": "string"}},
                    "test_size": {"type": "number", "default": 0.2},
                    "random_state": {"type": "integer", "default": 42},
                },
                "required": [],
            },
        },
        {
            "name": "select_best",
            "description": "Select the best model by a metric (R2, RMSE, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"metric": {"type": "string", "default": "R2"}},
                "required": [],
            },
        },
        {
            "name": "export_artifacts",
            "description": "Pickle the best model pipeline + metadata to /artifacts and return an ArtifactToken.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ]


# ── Tool implementations ──────────────────────────────────────────────────────

@app.post("/call/configure_run")
async def configure_run(request: Request) -> JSONResponse:
    body = await request.json()
    token_data = body.get("handoff_token", {})
    target_col = body.get("target_col", "buildingdamageamount")
    test_size = float(body.get("test_size", 0.2))
    random_state = int(body.get("random_state", 42))

    token = HandoffToken(**token_data)

    # Load data
    try:
        df_claims, df_parcels, df_values = _trainer.load_training_data()
        df_pred, zip_dist_map = _trainer.build_zip_dist_map(df_parcels, df_values)
        df_train_raw = _trainer.prepare_training_df(df_claims, zip_dist_map)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": f"Data load failed: {exc}"})

    df_enc, one_hot_cols = _trainer.encode_features(df_train_raw)
    feature_cols = ["property_value", "elevation", "flood_level", "zip_mean_dist"] + one_hot_cols
    X = df_enc[feature_cols]
    y = df_enc[target_col].values if target_col in df_enc.columns else df_enc["target"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    _run_state.update({
        "run_id": str(uuid.uuid4())[:8],
        "token": token,
        "df_pred": df_pred,
        "zip_dist_map": zip_dist_map,
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_cols": feature_cols,
        "one_hot_cols": one_hot_cols,
        "fitted_models": {},
        "metrics_df": None,
        "best_model": None,
        "best_metrics": None,
        "transform": None,
    })

    return JSONResponse(content={
        "status": "ok",
        "run_id": _run_state["run_id"],
        "X_train_shape": list(X_train.shape),
        "X_test_shape": list(X_test.shape),
        "feature_count": len(feature_cols),
    })


@app.post("/call/fit_gmm")
async def fit_gmm_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    n_components = int(body.get("n_components", 3))
    if "y_train" not in _run_state:
        return JSONResponse(status_code=400, content={"error": "Run not configured. Call configure_run first."})

    gmm, info = _trainer.fit_gmm(_run_state["y_train"], n_components)
    _run_state["gmm"] = gmm
    return JSONResponse(content={"aic": info["aic"], "bic": info["bic"], "n_components": n_components})


@app.post("/call/apply_transform")
async def apply_transform_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    method = body.get("method", "yeo-johnson")
    if "y_train" not in _run_state:
        return JSONResponse(status_code=400, content={"error": "Run not configured."})

    y_t, transformer = _trainer.apply_transform(_run_state["y_train"], method)
    _run_state["y_train_transformed"] = y_t
    _run_state["transform"] = transformer
    return JSONResponse(content={"method": method, "y_mean_transformed": float(y_t.mean())})


@app.post("/call/train_ensemble")
async def train_ensemble_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    model_names = body.get("models", None)
    if "X_train" not in _run_state:
        return JSONResponse(status_code=400, content={"error": "Run not configured."})

    y_train = _run_state.get("y_train_transformed", _run_state["y_train"])
    fitted = _trainer.train_models(_run_state["X_train"], y_train, model_names)
    _run_state["fitted_models"] = fitted

    metrics_df = _evaluator.evaluate_models(fitted, _run_state["X_test"], _run_state["y_test"])
    _run_state["metrics_df"] = metrics_df

    return JSONResponse(content={"models_trained": list(fitted.keys()), "metrics": metrics_df.to_dict(orient="records")})


@app.post("/call/select_best")
async def select_best_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    metric = body.get("metric", "R2")
    if _run_state.get("metrics_df") is None:
        return JSONResponse(status_code=400, content={"error": "No metrics yet. Call train_ensemble first."})

    best = _evaluator.select_best(_run_state["metrics_df"], metric)
    _run_state["best_metrics"] = best
    _run_state["best_model"] = _run_state["fitted_models"][best.model_name]
    return JSONResponse(content=best.model_dump())


@app.post("/call/export_artifacts")
async def export_artifacts_endpoint(request: Request) -> JSONResponse:
    if _run_state.get("best_model") is None:
        return JSONResponse(status_code=400, content={"error": "No best model selected. Call select_best first."})

    run_id = _run_state["run_id"]
    artifact_dir = ARTIFACTS_DIR / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(_run_state["best_model"], artifact_dir / "model.pkl")
    if _run_state.get("transform"):
        joblib.dump(_run_state["transform"], artifact_dir / "transformer.pkl")

    meta = {
        "run_id": run_id,
        "best_model_name": _run_state["best_metrics"].model_name,
        "feature_cols": _run_state["feature_cols"],
        "one_hot_cols": _run_state["one_hot_cols"],
        "zip_dist_map": _run_state["zip_dist_map"],
        "metrics": _run_state["best_metrics"].model_dump(),
    }
    with open(artifact_dir / "meta.json", "w") as f:
        json.dump(meta, f)

    token = ArtifactToken(
        run_id=run_id,
        artifact_dir=str(artifact_dir),
        best_model_name=_run_state["best_metrics"].model_name,
        metrics=_run_state["best_metrics"],
        feature_cols=_run_state["feature_cols"],
        zip_dist_map=_run_state["zip_dist_map"],
        one_hot_cols=_run_state["one_hot_cols"],
    )
    asyncio.ensure_future(write_audit("MEL", "export_artifacts", {"run_id": run_id}, f"artifact_dir={str(artifact_dir)}", "success"))
    return JSONResponse(content=token.model_dump(mode="json"))


# ── Generic call router ───────────────────────────────────────────────────────

@app.post("/call/{tool_name}")
async def call_tool(tool_name: str, request: Request) -> JSONResponse:
    route_map = {
        "configure_run": configure_run,
        "fit_gmm": fit_gmm_endpoint,
        "apply_transform": apply_transform_endpoint,
        "train_ensemble": train_ensemble_endpoint,
        "select_best": select_best_endpoint,
        "export_artifacts": export_artifacts_endpoint,
    }
    handler = route_map.get(tool_name)
    if handler is None:
        return JSONResponse(status_code=404, content={"error": f"Tool '{tool_name}' not found"})
    return await handler(request)
