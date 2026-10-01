"""Cliente MLflow y caché de modelos compartido por la API y el entrenamiento."""

import pickle
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import mlflow
import mlflow.tensorflow

from .config import MLFLOW_EXPERIMENT_NAME, MLFLOW_TRACKING_URI

MAX_CACHED_MODELS = 20
_model_cache: OrderedDict[int, dict] = OrderedDict()


def setup_mlflow() -> None:
    """Configura una sola vez la URI de tracking y el experimento activo."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)


def get_latest_run_id(station_id: int) -> Optional[str]:
    """Devuelve el run_id más reciente para la estación dada."""
    experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_NAME)
    if experiment is None:
        return None

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.`mlflow.runName` = 'est_{station_id}'",
        order_by=["start_time DESC"],
        max_results=1,
    )
    if runs.empty:
        return None
    return runs.iloc[0].run_id


def load_scaler(run_id: str, name: str):
    """Descarga y deserializa un scaler guardado como artifact de MLflow."""
    artifact_path = f"scalers/{name}.pkl"
    local_path = mlflow.artifacts.download_artifacts(
        run_id=run_id, artifact_path=artifact_path
    )
    with open(local_path, "rb") as f:
        return pickle.load(f)


def load_model_and_scalers(station_id: int, run_id: str) -> dict:
    """Devuelve modelo/scalers/feature_cols, cacheando en memoria por estación."""
    global _model_cache
    if station_id in _model_cache:
        entry = _model_cache.pop(station_id)
        _model_cache[station_id] = entry
        return entry

    model = mlflow.tensorflow.load_model(f"runs:/{run_id}/model")
    scaler_x = load_scaler(run_id, "scaler_x")
    scaler_y = load_scaler(run_id, "scaler_y")
    feature_cols = load_scaler(run_id, "feature_cols")

    entry = {
        "model": model,
        "scaler_x": scaler_x,
        "scaler_y": scaler_y,
        "feature_cols": feature_cols,
    }

    if len(_model_cache) >= MAX_CACHED_MODELS:
        _model_cache.popitem(last=False)
    _model_cache[station_id] = entry
    return entry


__all__ = [
    "setup_mlflow",
    "get_latest_run_id",
    "load_scaler",
    "load_model_and_scalers",
    "MAX_CACHED_MODELS",
]
