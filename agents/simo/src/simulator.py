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
    feature_cols: List[str],
) -> pd.DataFrame:
    """Build the feature matrix for the parcel dataset at a given flood level."""
    d = df.copy()

    # Ensure required columns exist
    if "elevation_ft" not in d.columns and "elevation" in d.columns:
        d["elevation_ft"] = d["elevation"] * METERS_TO_FEET
        d = d.drop(columns=["elevation"])

    d["flood_level"] = flood_level_ft
    d["zip_mean_dist"] = d["zip_code"].map(zip_dist_map).fillna(
        np.mean(list(zip_dist_map.values()))
    )

    # Vectorized One-Hot Encoding for ZIP codes
    for col in one_hot_cols:
        zip_val = col.replace("zip_", "")
        d[col] = (d["zip_code"].astype(str) == zip_val).astype(int)

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
    feature_cols: List[str],
    value_table: Optional[str] = None,
    value_col: Optional[str] = None,
    parcel_table: str = "public.parcels_cliplayer",
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

    # Load parcels — use real columns with COALESCE fallbacks.
    # We join with parcels_cliplayer ONLY if parcel_table is NOT that table, 
    # to ensure we always have ZCTA/Elevation if the provided table is sparse.
    async with pool.acquire() as conn:
        if value_table and value_col:
            # Join with custom table for real property values.
            # We use a TRY-CAST logic by filtering out non-numeric FLNs if possible,
            # but standard SQL cast is fine if data is clean.
            query = f"""
            SELECT
                p.gid,
                p."FLN"                                        AS parcel_id,
                COALESCE(p.elev_mean::float8, 5.0)              AS elevation,
                COALESCE(p."ZCTA5CE20"::text, '00000')         AS zip_code,
                COALESCE(v."{value_col}"::float8, 200000.0)    AS property_value
            FROM {parcel_table} p
            LEFT JOIN {value_table} v ON v.parcelid::text = p."FLN"::text
            WHERE p."FLN" IS NOT NULL
            LIMIT 500000
            """
        else:
            query = f"""
            SELECT
                p.gid,
                p."FLN"                                        AS parcel_id,
                COALESCE(p.elev_mean::float8, 5.0)              AS elevation,
                COALESCE(p."ZCTA5CE20"::text, '00000')         AS zip_code,
                200000.0::float8                               AS property_value
            FROM {parcel_table} p
            WHERE p."FLN" IS NOT NULL
            LIMIT 500000
            """
        try:
            rows = await conn.fetch(query)
        except Exception as e:
             # Fallback: if 'p' doesn't have elev_mean or ZCTA, try joining with cliplayer
             if "elev_mean" in str(e) or "ZCTA5CE20" in str(e):
                query = f"""
                SELECT
                    p.gid,
                    p."FLN"                                        AS parcel_id,
                    COALESCE(orig.elev_mean::float8, 5.0)           AS elevation,
                    COALESCE(orig."ZCTA5CE20"::text, '00000')      AS zip_code,
                    {'v."' + value_col + '"::float8' if value_table else '200000.0::float8'} AS property_value
                FROM {parcel_table} p
                JOIN public.parcels_cliplayer orig ON orig.gid = p.gid
                {f'JOIN {value_table} v ON v.parcelid = CASE WHEN p."FLN" ~ "^[0-9]+$" THEN p."FLN"::bigint ELSE NULL END' if value_table else ''}
                LIMIT 500000
                """
                rows = await conn.fetch(query)
             else:
                raise e

    if not rows:
        return {"error": "No parcels found in parcels_cliplayer"}

    df_base = pd.DataFrame([dict(r) for r in rows])
    # Cast/Clean zip code
    df_base["zip_code"] = df_base["zip_code"].astype(str).str.replace(r"\.0$", "", regex=True)

    results_by_level: Dict[str, Any] = {}
    all_records: List[Dict[str, Any]] = []

    for level in flood_levels:
        X = _build_parcel_features(df_base, level, zip_dist_map, one_hot_cols, feature_cols)
        
        # Debug logging
        print(f"[SIMO] Level {level}ft features shape: {X.shape}")
        if not X.empty:
            print(f"[SIMO] Mean property_value: {X['property_value'].mean():.2f}")
            print(f"[SIMO] Mean elevation: {X['elevation'].mean():.2f}")
        
        raw_preds = model.predict(X)
        print(f"[SIMO] Raw predictions (mean): {raw_preds.mean():.4f}, (max): {raw_preds.max():.4f}, (min): {raw_preds.min():.4f}")
        
        preds = np.maximum(raw_preds, 0.0)
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
