import mlflow
import mysql.connector
import numpy as np
import pandas as pd

from backend.core.config import MLFLOW_EXPERIMENT_NAME
from backend.core.db import DB_NAME, get_connection_params
from backend.core.features import bicis
from backend.core.mlflow_client import load_model_and_scalers
from backend.core.model import HORIZONTES_MIN, LOOKBACK, LSTMbicis, STEP_MINUTES, TARGET_COLS

STATION_COLUMNS = ["station_id", "latitud", "longitud", "address", "post_code", "capacity"]
EXCLUDED_STATION_IDS = (521, 529, 545)


class ResourceNotFoundError(Exception):
    pass


def get_stations() -> dict:
    station_ids = _get_registered_station_ids()
    if not station_ids:
        return {}

    placeholders = ", ".join("%s" for _ in station_ids)
    excluded_placeholders = ", ".join("%s" for _ in EXCLUDED_STATION_IDS)
    query = f"""
        SELECT {", ".join(STATION_COLUMNS)}
        FROM informacion
        WHERE station_id IN ({placeholders})
          AND station_id NOT IN ({excluded_placeholders})
    """
    params = (*sorted(station_ids), *EXCLUDED_STATION_IDS)

    connection = mysql.connector.connect(**get_connection_params(DB_NAME))
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

    return {
        row["station_id"]: {key: value for key, value in row.items() if key != "station_id"}
        for row in rows
    }


def predict_availability(station_id: int) -> dict:
    run_id = _get_latest_run_id(station_id)
    cached = load_model_and_scalers(station_id, run_id)
    model = cached["model"]
    scaler_x = cached["scaler_x"]
    scaler_y = cached["scaler_y"]
    feature_cols = cached["feature_cols"]

    latest_timestamp = _get_latest_station_timestamp(station_id)
    since = (pd.Timestamp(latest_timestamp) - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    df = bicis(station_id, since=since)

    feature_frame, _ = LSTMbicis(station_id=station_id).preparar_datos(df)
    feature_frame = feature_frame[feature_cols]
    if len(feature_frame) < LOOKBACK:
        raise ResourceNotFoundError(
            f"La estación {station_id} no tiene suficientes datos para predecir"
        )

    scaled_features = scaler_x.transform(feature_frame)
    latest_window = scaled_features[-LOOKBACK:].reshape(1, LOOKBACK, len(feature_cols))
    horizon_steps = [horizon // STEP_MINUTES for horizon in HORIZONTES_MIN]
    scaled_prediction = model.predict_on_batch(np.float32(latest_window))[0]
    prediction_matrix = scaler_y.inverse_transform(
        scaled_prediction.reshape(len(horizon_steps), len(TARGET_COLS))
    )

    last_timestamp = df.index[-1]
    predictions = []
    for horizon, row in zip(HORIZONTES_MIN, prediction_matrix):
        prediction_timestamp = last_timestamp + pd.Timedelta(minutes=horizon)
        mechanical, electric = np.maximum(row, 0)
        predictions.append(
            {
                "horizon_minutes": int(horizon),
                "timestamp": prediction_timestamp.isoformat(),
                "nbm": float(mechanical),
                "nbe": float(electric),
            }
        )

    return {
        "station_id": station_id,
        "last_timestamp": last_timestamp.isoformat(),
        "predictions": predictions,
    }


def _get_registered_station_ids() -> set[int]:
    client = mlflow.MlflowClient()
    return {
        int(model.name.removeprefix("est_"))
        for model in client.search_registered_models(max_results=1000)
        if model.name.startswith("est_") and model.name.removeprefix("est_").isdigit()
    }


def _get_latest_run_id(station_id: int) -> str:
    experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_NAME)
    if experiment is None:
        raise ResourceNotFoundError("Experimento de MLflow no encontrado")

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.`mlflow.runName` = 'est_{station_id}'",
        order_by=["start_time DESC"],
        max_results=1,
    )
    if runs.empty:
        raise ResourceNotFoundError(
            f"No se encontró modelo entrenado para la estación {station_id}"
        )
    return runs.iloc[0].run_id


def _get_latest_station_timestamp(station_id: int):
    connection = mysql.connector.connect(**get_connection_params(DB_NAME))
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT MAX(datetime) FROM estado WHERE station_id = %s",
            (station_id,),
        )
        latest_timestamp = cursor.fetchone()[0]
        cursor.close()
    finally:
        connection.close()

    if latest_timestamp is None:
        raise ResourceNotFoundError(
            f"La estación {station_id} no tiene datos históricos"
        )
    return latest_timestamp
