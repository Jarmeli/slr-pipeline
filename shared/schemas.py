"""Pydantic contracts for inter-agent handoffs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TableInfo(BaseModel):
    name: str
    schema: str
    row_count: int
    columns: List[str]


class HandoffToken(BaseModel):
    """Produced by DIO → consumed by MEL."""
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    schema_name: str = "clean_data"
    tables: List[TableInfo]
    feature_cols: List[str] = []
    target_col: str = "buildingdamageamount"
    notes: Optional[str] = None


class ModelMetrics(BaseModel):
    model_name: str
    r2: float
    adj_r2: float
    mse: float
    rmse: float


class ArtifactToken(BaseModel):
    """Produced by MEL → consumed by SIMO."""
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    run_id: str
    artifact_dir: str                   # absolute path inside /artifacts volume
    best_model_name: str
    metrics: ModelMetrics
    feature_cols: List[str]
    zip_dist_map: Dict[str, float]      # zip_code → mean distance_to_water
    one_hot_cols: List[str]
    notes: Optional[str] = None


class SimulationResult(BaseModel):
    """Returned by SIMO.run_simulation()."""
    run_id: str
    flood_levels: List[float]
    total_parcels: int
    results_by_level: Dict[str, Any]   # level_str → {total_exposure, mean_damage, parcel_count}
