"""MEL Evaluator — metrics computation and model selection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, r2_score

from shared.schemas import ModelMetrics


def evaluate_models(
    fitted_models: Dict[str, Any],
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    transformer: Any = None,
) -> pd.DataFrame:
    """Return a DataFrame with R², Adj-R², MSE, RMSE for each model.

    If a power transformer (e.g. Yeo-Johnson) was used during training,
    pass it here so predictions are inverse-transformed back to the original
    dollar scale before metrics are computed against y_test.
    """
    n = X_test.shape[0]
    k = X_test.shape[1]
    rows = []
    for name, model in fitted_models.items():
        raw_preds = model.predict(X_test)

        # Inverse-transform if the model was trained on a transformed target
        if transformer is not None and hasattr(transformer, "inverse_transform"):
            preds = transformer.inverse_transform(raw_preds.reshape(-1, 1)).ravel()
        elif transformer == ("log",):
            preds = np.expm1(raw_preds)
        else:
            preds = raw_preds

        preds = np.maximum(preds, 0)
        r2 = r2_score(y_test, preds)
        mse = mean_squared_error(y_test, preds)
        rmse = float(np.sqrt(mse))
        adj_r2 = 1 - (1 - r2) * (n - 1) / (n - k - 1) if (n - k - 1) > 0 else float("nan")
        rows.append(
            {
                "model_name": name,
                "R2": round(r2, 4),
                "Adj_R2": round(adj_r2, 4),
                "MSE": round(mse, 2),
                "RMSE": round(rmse, 2),
            }
        )
    df = pd.DataFrame(rows).sort_values("R2", ascending=False).reset_index(drop=True)
    return df



def select_best(metrics_df: pd.DataFrame, metric: str = "R2") -> ModelMetrics:
    """Pick the best model by the given metric column."""
    best = metrics_df.sort_values(metric, ascending=False).iloc[0]
    return ModelMetrics(
        model_name=best["model_name"],
        r2=float(best["R2"]),
        adj_r2=float(best["Adj_R2"]),
        mse=float(best["MSE"]),
        rmse=float(best["RMSE"]),
    )


def residual_summary(
    model: Any,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
) -> Dict[str, float]:
    """Return basic residual statistics."""
    preds = np.maximum(model.predict(X_test), 0)
    residuals = y_test - preds
    return {
        "mean_residual": float(residuals.mean()),
        "std_residual": float(residuals.std()),
        "max_overestimate": float(residuals.min()),
        "max_underestimate": float(residuals.max()),
    }
