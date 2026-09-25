"""
API REST (Flask) que expone la información de las estaciones Bicing y las
predicciones de disponibilidad de bicis (mecánicas y eléctricas) a 5 y
10 minutos para una estación dada.

Endpoints disponibles:
    GET /api/informacion  -> lista de estaciones con modelo registrado en MLflow:
        station_id, latitud, longitud, address, post_code, capacity

    POST /api/predict
        Body JSON: { "station_id": <int> }
        Respuesta: { "station_id": ..., "last_timestamp": ..., "predictions": [...] }

Las credenciales de acceso a MySQL se leen desde el archivo `.env` en la
raíz del proyecto, a través de `backend/scripts/silver/db_config.py`.
"""

import pickle
import sys
import traceback
from pathlib import Path

import mlflow
import mlflow.tensorflow
import mysql.connector
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "silver"))
from db_config import DB_NAME, get_connection_params

# Añadimos al path la carpeta que contiene lstm_model.py (backend/scripts).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lstm_model import HORIZONTES_MIN, LOOKBACK, LSTMbicis, STEP_MINUTES, TARGET_COLS

MLFLOW_TRACKING_URI = "http://localhost:5000"
MLFLOW_EXPERIMENT_NAME = "bicing_lstm_predictions"

app = Flask(__name__)
CORS(app)  # Permite que el frontend (React, otro origen) consuma esta API

COLUMNS = ["station_id", "latitud", "longitud", "address", "post_code", "capacity"]

# Cache LRU en memoria para modelos/scalers ya cargados. Cada estación repite
# los mismos artifacts de MLflow, por lo que cachearlos evita descargar el
# modelo Keras en cada petición de predicción.
from collections import OrderedDict

MAX_CACHED_MODELS = 20
_model_cache: OrderedDict[int, dict] = OrderedDict()

# Configurar MLflow una sola vez al iniciar la API.
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)


def _obtener_estaciones_con_modelo():
    """Devuelve los station_id que tienen un modelo registrado en MLflow."""
    client = mlflow.MlflowClient()
    return {
        int(modelo.name.replace("est_", ""))
        for modelo in client.search_registered_models(max_results=1000)
        if modelo.name.startswith("est_") and modelo.name.replace("est_", "").isdigit()
    }


@app.route("/api/informacion", methods=["GET"])
def obtener_informacion():
    """Devuelve, en formato JSON, las estaciones que tienen modelo en MLflow."""
    estaciones_con_modelo = _obtener_estaciones_con_modelo()
    if not estaciones_con_modelo:
        return jsonify({})

    placeholders = ", ".join("%s" for _ in estaciones_con_modelo)
    query = f"""
    SELECT {", ".join(COLUMNS)}
    FROM informacion
    WHERE station_id IN ({placeholders}) AND station_id NOT IN (521,529,545)
    """
    conn = mysql.connector.connect(**get_connection_params(DB_NAME))
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(sorted(estaciones_con_modelo)))
        filas = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()

    estaciones = {
        fila["station_id"]: {k: v for k, v in fila.items() if k != "station_id"}
        for fila in filas
    }

    return jsonify(estaciones)


def _cargar_run_reciente(station_id: int):
    """Busca el run de MLflow más reciente para la estación dada."""
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


def _cargar_scaler(run_id: str, nombre: str):
    """Descarga y deserializa un scaler guardado como artifact de MLflow."""
    artifact_path = f"scalers/{nombre}.pkl"
    local_path = mlflow.artifacts.download_artifacts(
        run_id=run_id, artifact_path=artifact_path
    )
    with open(local_path, "rb") as f:
        return pickle.load(f)


def _cargar_modelo_cache(station_id: int, run_id: str):
    """Devuelve modelo/scalers/feature_cols, cacheando en memoria por estación."""
    global _model_cache
    if station_id in _model_cache:
        # Mover al final para mantener política LRU.
        entry = _model_cache.pop(station_id)
        _model_cache[station_id] = entry
        return entry

    model = mlflow.tensorflow.load_model(f"runs:/{run_id}/model")
    scaler_x = _cargar_scaler(run_id, "scaler_x")
    scaler_y = _cargar_scaler(run_id, "scaler_y")
    feature_cols = _cargar_scaler(run_id, "feature_cols")

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


@app.route("/api/predict", methods=["POST"])
def predict():
    """Recibe station_id y devuelve las predicciones de nbm y nbe a 5 y 10 min."""
    data = request.get_json(silent=True) or {}
    station_id = data.get("station_id")

    if station_id is None:
        return jsonify({"error": "station_id es obligatorio"}), 400

    try:
        station_id = int(station_id)
    except (ValueError, TypeError):
        return jsonify({"error": "station_id debe ser un número entero"}), 400

    try:
        run_id = _cargar_run_reciente(station_id)
        if run_id is None:
            return jsonify(
                {"error": f"No se encontró modelo entrenado para la estación {station_id}"}
            ), 404

        # Cargar modelo y escaladores desde MLflow (con cache en memoria).
        cached = _cargar_modelo_cache(station_id, run_id)
        model = cached["model"]
        scaler_x = cached["scaler_x"]
        scaler_y = cached["scaler_y"]
        feature_cols = cached["feature_cols"]

        # Obtener datos históricos de la estación.
        bicis = LSTMbicis._import_bicis()
        df = bicis(station_id)

        # Preparar features con la misma lógica usada en entrenamiento.
        modelo = LSTMbicis(station_id=station_id)
        df_features, _ = modelo.preparar_datos(df)
        df_features = df_features[feature_cols]

        # Escalar y construir la última ventana de entrada.
        features_scaled = scaler_x.transform(df_features)
        ultima_ventana = features_scaled[-LOOKBACK:].reshape(
            1, LOOKBACK, len(feature_cols)
        )

        # Predecir y desescalar. Se usa predict_on_batch en lugar de predict
        # para reducir el overhead y el retracing continuo de tf.function al
        # alternar entre modelos de distintas estaciones.
        horizon_steps = [h // STEP_MINUTES for h in HORIZONTES_MIN]
        pred_scaled = model.predict_on_batch(np.float32(ultima_ventana))[0]
        pred_matrix_scaled = pred_scaled.reshape(len(horizon_steps), len(TARGET_COLS))
        pred_matrix = scaler_y.inverse_transform(pred_matrix_scaled)

        ultimo_timestamp = df.index[-1]
        predictions = []
        for h_min, fila in zip(HORIZONTES_MIN, pred_matrix):
            pred_dt = ultimo_timestamp + pd.Timedelta(minutes=h_min)
            mech_pred, ebike_pred = np.maximum(fila, 0)
            predictions.append(
                {
                    "horizon_minutes": int(h_min),
                    "timestamp": pred_dt.isoformat(),
                    "nbm": float(mech_pred),
                    "nbe": float(ebike_pred),
                }
            )

        return jsonify({
            "station_id": station_id,
            "last_timestamp": ultimo_timestamp.isoformat(),
            "predictions": predictions,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # debug=False evita el recargador de Flask, que en Windows puede detectar
    # cambios en archivos del sistema y reiniciar el proceso constantemente.
    app.run(host="0.0.0.0", port=5002, debug=False)
