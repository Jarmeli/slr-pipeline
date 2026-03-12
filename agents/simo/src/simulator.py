"""SIMO Flood Simulation Engine.

Loads a trained model from /artifacts, applies it to every parcel in the DB,
and writes results to the parcel_damage table (compatible with the existing
RookeryBay web app schema).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

METERS_TO_FEET = 3.28084
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/artifacts"))


def load_artifact(artifact_dir: str) -> Dict[str, Any]:
    """Load model, optional transformer, and metadata from an artifact directory."""
    d = Path(artifact_dir)
    model = joblib.load(d / "model.pkl")
    transformer = None
    if (d / "transformer.pkl").exists():
        transformer = joblib.load(d / "transformer.pkl")
    with open(d / "meta.json") as f:
        meta = json.load(f)
    return {"model": model, "transformer": transformer, "meta": meta}


def _build_parcel_features(
    df: pd.DataFrame,
    flood_level_ft: float,
    zip_dist_map: Dict[str, float],
    one_hot_cols: List[str],
) -> pd.DataFrame:
    """Build the feature matrix for the parcel dataset at a given flood level."""
    d = df.copy()

    # Ensure required columns exist
    if "elevation_ft" not in d.columns and "elevation" in d.columns:
        d["elevation_ft"] = d["elevation"] * METERS_TO_FEET

    d["flood_level"] = flood_level_ft
    d["zip_mean_dist"] = d["zip_code"].map(zip_dist_map).fillna(
        np.mean(list(zip_dist_map.values()))
    )

    # Seed one-hot columns with zeros, fill known values
    for col in one_hot_cols:
        d[col] = 0

    # Map zip_code → one-hot column
    for _, row in d.iterrows():
        zc = f"zip_{row['zip_code']}"
        if zc in d.columns:
            d.loc[_, zc] = 1

    base_cols = ["property_value", "elevation_ft", "flood_level", "zip_mean_dist"]
    # Rename elevation_ft → elevation to match training feature name
    feature_cols = ["property_value", "elevation", "flood_level", "zip_mean_dist"] + one_hot_cols
    d = d.rename(columns={"elevation_ft": "elevation"})

    # Ensure all feature cols are present
    for col in feature_cols:
        if col not in d.columns:
            d[col] = 0.0

    return d[feature_cols].fillna(0.0)


async def run_simulation(
    artifact_dir: str,
    flood_levels: List[float],
    zip_dist_map: Dict[str, float],
    one_hot_cols: List[str],
) -> Dict[str, Any]:
    """
    Run flood damage simulation for each level and write to parcel_damage table.
    Returns summary dict.
    """
    from shared.db import get_pool

    artifact = load_artifact(artifact_dir)
    model = artifact["model"]
    run_id = str(uuid.uuid4())[:8]

    pool = await get_pool()

    # Load parcels
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.gid,
                p."FLN"           AS parcel_id,
                p.elev_mean       AS elevation,
                p."ZCTA5CE20"     AS zip_code,
                p.geometry
            FROM public.parcels_cliplayer p
            LIMIT 500000
            """
        )

    if not rows:
        return {"error": "No parcels found in parcels_cliplayer"}

    df_base = pd.DataFrame([dict(r) for r in rows])
    df_base["property_value"] = 200000.0  # placeholder; replace with real values if joined
    df_base["zip_code"] = df_base["zip_code"].astype(str).str.replace(r"\.0$", "", regex=True)

    results_by_level: Dict[str, Any] = {}
    all_records: List[Dict[str, Any]] = []

    for level in flood_levels:
        X = _build_parcel_features(df_base, level, zip_dist_map, one_hot_cols)
        preds = np.maximum(model.predict(X), 0.0)
        df_base[f"pred_{level}ft"] = preds

        results_by_level[f"{level}ft"] = {
            "flood_level_ft": level,
            "parcel_count": len(preds),
            "total_exposure": float(preds.sum()),
            "mean_damage": float(preds.mean()),
            "median_damage": float(np.median(preds)),
        }

        for gid, pred in zip(df_base["gid"], preds):
            all_records.append({
                "parcel_gid": int(gid),
                "flood_level": float(level),
                "predicted_damage": float(pred),
                "run_id": run_id,
            })

    # Write to parcel_damage
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parcel_damage (
                id               BIGSERIAL PRIMARY KEY,
                parcel_gid       INTEGER,
                flood_level      NUMERIC,
                predicted_damage NUMERIC,
                run_id           TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        # Delete old predictions for same run
        await conn.execute("DELETE FROM parcel_damage WHERE run_id = $1", run_id)
        await conn.copy_records_to_table(
            "parcel_damage",
            records=[
                (r["parcel_gid"], r["flood_level"], r["predicted_damage"], r["run_id"])
                for r in all_records
            ],
            columns=["parcel_gid", "flood_level", "predicted_damage", "run_id"],
        )

    return {
        "run_id": run_id,
        "flood_levels": flood_levels,
        "total_parcels": len(df_base),
        "results_by_level": results_by_level,
    }


async def invalidate_tile_cache(levels: Optional[List[float]] = None) -> Dict[str, int]:
    """Delete cached tiles for damage layers so the web app reloads fresh data."""
    from shared.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        if levels:
            patterns = [f"damage_{int(l)}ft" for l in levels] + [f"damage_{l}ft" for l in levels]
            deleted = 0
            for pattern in patterns:
                result = await conn.execute("DELETE FROM tile_cache WHERE layer = $1", pattern)
                deleted += int(result.split()[-1])
        else:
            result = await conn.execute("DELETE FROM tile_cache WHERE layer LIKE 'damage%'")
            deleted = int(result.split()[-1])

    return {"tiles_invalidated": deleted}
