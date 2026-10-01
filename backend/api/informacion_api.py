"""API REST (Flask) que expone la información de las estaciones Bicing y las
predicciones de disponibilidad de bicis (mecánicas y eléctricas) a 5 y
10 minutos para una estación dada.

Endpoints disponibles:
    GET /api/informacion  -> lista de estaciones con modelo registrado en MLflow:
        station_id, latitud, longitud, address, post_code, capacity

    POST /api/predict
        Body JSON: { "station_id": <int> }
        Respuesta: { "station_id": ..., "last_timestamp": ..., "predictions": [...] }

Las credenciales de acceso a MySQL se leen desde el archivo `.env` en la
raíz del proyecto, a través de `backend/core/db.py`.
"""

import traceback
from pathlib import Path

import mysql.connector
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import MLFLOW_EXPERIMENT_NAME, MLFLOW_TRACKING_URI
from core.db import DB_NAME, get_connection_params
from core.features import bicis
from core.mlflow_client import load_model_and_scalers, setup_mlflow
from core.model import HORIZONTES_MIN, LOOKBACK, LSTMbicis, STEP_MINUTES, TARGET_COLS
import mlflow

app = Flask(__name__)
CORS(app)  # Permite que el frontend (React, otro origen) consuma esta API

COLUMNS = ["station_id", "latitud", "longitud", "address", "post_code", "capacity"]

# Configurar MLflow una sola vez al iniciar la API.
setup_mlflow()


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
        experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_NAME)
        if experiment is None:
            return jsonify({"error": "Experimento de MLflow no encontrado"}), 404

        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=f"tags.`mlflow.runName` = 'est_{station_id}'",
            order_by=["start_time DESC"],
            max_results=1,
        )
        if runs.empty:
            return jsonify(
                {"error": f"No se encontró modelo entrenado para la estación {station_id}"}
            ), 404

        run_id = runs.iloc[0].run_id

        # Cargar modelo y escaladores desde MLflow (con cache en memoria).
        cached = load_model_and_scalers(station_id, run_id)
        model = cached["model"]
        scaler_x = cached["scaler_x"]
        scaler_y = cached["scaler_y"]
        feature_cols = cached["feature_cols"]

        # Obtener datos recientes de la estación. Solo hace falta el
        # histórico suficiente para la ventana LOOKBACK (24 pasos = 2 h)
        # más margen por lags e imputación. Como el histórico termina en
        # una fecha fija, `since` se calcula respecto al MAX(datetime) de
        # la tabla, no respecto a la fecha actual.
        conn = mysql.connector.connect(**get_connection_params(DB_NAME))
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(datetime) FROM estado WHERE station_id = %s",
                (station_id,),
            )
            ultimo_dt = cursor.fetchone()[0]
            cursor.close()
        finally:
            conn.close()

        if ultimo_dt is None:
            return jsonify(
                {"error": f"La estación {station_id} no tiene datos históricos"}
            ), 404

        desde = (pd.Timestamp(ultimo_dt) - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        df = bicis(station_id, since=desde)

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
    # threaded=True permite atender peticiones concurrentes, evitando que una
    # predicción lenta bloquee las siguientes.
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
