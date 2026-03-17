"""MEL Training Engine — refactored from collier_ensemble.ipynb and Gaussian.ipynb."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import (
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import PowerTransformer

METERS_TO_FEET = 3.28084
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_training_data(data_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load claims, parcels, and property values from CSV files."""
    d = data_dir or DATA_DIR
    df_claims = pd.read_csv(d / "collier_claims_cleaned.csv")
    df_parcels = pd.read_csv(d / "parcels.csv", low_memory=False)
    df_values = pd.read_csv(d / "Real_Property_Values.csv", header=None, low_memory=False)
    return df_claims, df_parcels, df_values


def load_from_db_token(token_tables: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Load claims from clean_data schema when a HandoffToken is provided.
    Returns a DataFrame of clean claims.
    """
    import asyncio
    from shared.db import get_pool

    async def _fetch() -> pd.DataFrame:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM clean_data.claims_processed LIMIT 100000')
        return pd.DataFrame([dict(r) for r in rows])

    return asyncio.run(_fetch())


async def prepare_from_db(token_tables: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, float], pd.DataFrame]:
    """
    Load and prepare training data entirely from clean_data.claims_processed.
    Used as fallback when CSV files are unavailable.

    DIO writes every column as TEXT, so numeric casts happen here.
    zip_mean_dist is derived from the claims data (mean waterdepth per zip code).

    Returns (df_train_raw, zip_dist_map, df_pred).
    """
    from shared.db import get_pool

    table_name = "claims_processed"
    schema_name = "clean_data"
    if token_tables:
        table_name = token_tables[0]["name"]
        schema_name = token_tables[0].get("schema", "clean_data")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT 100000')
    df = pd.DataFrame([dict(r) for r in rows])

    # Cast columns that were stored as TEXT by DIO
    numeric_cols = [
        "buildingdamageamount", "buildingpropertyvalue", "waterdepth",
        "lowestfloorelevation", "totalbuildinginsurancecoverage",
        "totalcontentsinsurancecoverage", "amountpaidonbuildingclaim",
        "amountpaidoncontentsclaim", "latitude", "longitude",
        "basefloodelevation", "elevationdifference", "lowestadjacentgrade",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.rename(columns={
        "buildingdamageamount": "target",
        "buildingpropertyvalue": "property_value",
        "waterdepth": "flood_level",
        "reportedzipcode": "zip_code",
        "lowestfloorelevation": "elevation",
    })

    df = df.dropna(subset=["target", "property_value", "zip_code", "elevation", "flood_level"])
    df["zip_code"] = df["zip_code"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Derive zip_mean_dist from claims: mean flood depth per zip code as proxy for
    # mean distance to water (used consistently across train / predict)
    zip_dist_map: Dict[str, float] = df.groupby("zip_code")["flood_level"].mean().to_dict()
    df["zip_mean_dist"] = df["zip_code"].map(zip_dist_map).fillna(0.0)

    df_pred = df[["property_value", "elevation", "zip_code", "zip_mean_dist"]].copy()
    df_pred["elevation_ft"] = df_pred["elevation"].fillna(0.0) * METERS_TO_FEET

    return df, zip_dist_map, df_pred


# ── Feature engineering ───────────────────────────────────────────────────────

def build_zip_dist_map(df_parcels: pd.DataFrame, df_values: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Construct df_pred (parcels enriched with property values) and zip→mean-distance map."""
    val_cols = {1: "parcel_id", 6: "property_value"}
    df_values_clean = df_values[[1, 6]].rename(columns=val_cols)
    df_values_clean["parcel_id"] = (
        df_values_clean["parcel_id"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df_values_clean["property_value"] = pd.to_numeric(df_values_clean["property_value"], errors="coerce")

    df_parcels = df_parcels.copy()
    df_parcels["parcel_id"] = (
        df_parcels["FLN"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df_pred = pd.merge(df_parcels, df_values_clean, on="parcel_id", how="left")
    df_pred = df_pred.rename(
        columns={"ZCTA5CE20": "zip_code", "elev_mean": "elevation", "distance": "distance_to_water"}
    )
    df_pred = df_pred.dropna(subset=["property_value", "zip_code", "elevation", "distance_to_water"])
    df_pred["zip_code"] = df_pred["zip_code"].astype(str).str.replace(r"\.0$", "", regex=True)
    zip_dist_map = df_pred.groupby("zip_code")["distance_to_water"].mean().to_dict()
    df_pred["zip_mean_dist"] = df_pred["zip_code"].map(zip_dist_map)
    df_pred["elevation_ft"] = df_pred["elevation"] * METERS_TO_FEET
    return df_pred, zip_dist_map


def prepare_training_df(df_claims: pd.DataFrame, zip_dist_map: Dict[str, float]) -> pd.DataFrame:
    df = df_claims.copy()
    df = df.rename(
        columns={
            "buildingdamageamount": "target",
            "buildingpropertyvalue": "property_value",
            "waterdepth": "flood_level",
            "reportedzipcode": "zip_code",
            "lowestfloorelevation": "elevation",
            "occupancytype": "occupancytype",
            "ratedfloodzone": "ratedfloodzone",
            "causeofdamage": "causeofdamage",
        }
    )
    df = df.dropna(subset=["target", "property_value", "zip_code", "elevation"])
    df["zip_code"] = df["zip_code"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["zip_mean_dist"] = df["zip_code"].map(zip_dist_map)
    df = df.dropna(subset=["zip_mean_dist"])
    return df


def encode_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """One-hot encode categorical columns; return encoded DataFrame and one_hot_cols list."""
    d = df.copy()
    zip_dummies = pd.get_dummies(d["zip_code"], prefix="zip")
    occ_dummies = pd.get_dummies(d["occupancytype"], prefix="occupancy")
    cod_dummies = pd.get_dummies(d["causeofdamage"], prefix="causeofdamage")
    fz_dummies = pd.get_dummies(d["ratedfloodzone"], prefix="ratedfloodzone")
    d = pd.concat(
        [d.drop(["zip_code", "occupancytype", "causeofdamage", "ratedfloodzone"], axis=1),
         zip_dummies, occ_dummies, cod_dummies, fz_dummies],
        axis=1,
    )
    one_hot_cols = [
        c for c in d.columns
        if (c.startswith("zip_") and c != "zip_mean_dist")
        or c.startswith(("occupancy_", "causeofdamage_", "ratedfloodzone_"))
    ]
    return d, one_hot_cols


# ── Target transformation (GMM-guided) ────────────────────────────────────────

def fit_gmm(y: np.ndarray, n_components: int = 3) -> Tuple[GaussianMixture, Dict[str, Any]]:
    """Fit a Gaussian Mixture Model on the target variable."""
    gmm = GaussianMixture(n_components=n_components, random_state=42)
    y_reshaped = y.reshape(-1, 1)
    gmm.fit(y_reshaped)
    aic = gmm.aic(y_reshaped)
    bic = gmm.bic(y_reshaped)
    labels = gmm.predict(y_reshaped).tolist()
    return gmm, {"aic": float(aic), "bic": float(bic), "n_components": n_components, "labels": labels}


def apply_transform(y: np.ndarray, method: str = "yeo-johnson") -> Tuple[np.ndarray, Any]:
    """Apply a power transform to the target; return transformed values and fitted transformer."""
    if method == "log":
        y_t = np.log1p(y)
        return y_t, ("log",)
    pt = PowerTransformer(method=method)
    y_t = pt.fit_transform(y.reshape(-1, 1)).ravel()
    return y_t, pt


# ── Model training ────────────────────────────────────────────────────────────

def build_models(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    defaults = params or {}
    return {
        "Random Forest": RandomForestRegressor(
            n_estimators=defaults.get("n_estimators", 500),
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=defaults.get("n_estimators", 500),
            random_state=42,
        ),
        "Hist Gradient Boosting": HistGradientBoostingRegressor(
            loss="squared_error",
            max_iter=defaults.get("n_estimators", 500),
            random_state=42,
        ),
    }


def train_models(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    model_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Train selected models. Returns dict of {name: fitted_model}."""
    all_models = build_models()
    to_train = {k: v for k, v in all_models.items() if model_names is None or k in model_names}
    fitted: Dict[str, Any] = {}
    for name, model in to_train.items():
        model.fit(X_train, y_train)
        fitted[name] = model
    return fitted
