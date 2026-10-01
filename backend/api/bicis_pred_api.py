"""API REST (Flask) que expone las predicciones de disponibilidad de bicis
(mecánicas y eléctricas) a 5 y 10 minutos para una estación Bicing dada.

Endpoint disponible:
    POST /api/predict
    Body JSON: { "station_id": <int> }

Respuesta JSON:
    {
        "station_id": <int>,
        "last_timestamp": <str ISO-8601>,
        "predictions": [
            {"horizon_minutes": 5, "timestamp": <str>, "nbm": <float>, "nbe": <float>},
            {"horizon_minutes": 10, "timestamp": <str>, "nbm": <float>, "nbe": <float>}
        ]
    }

El endpoint carga el modelo LSTM ya entrenado y registrado en MLflow bajo el
nombre "est_{station_id}" junto con sus escaladores. No reentrena el modelo,
por lo que la respuesta es casi inmediata.
"""

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mlflow
from core.config import MLFLOW_EXPERIMENT_NAME
from core.features import bicis
from core.mlflow_client import load_model_and_scalers, setup_mlflow
from core.model import HORIZONTES_MIN, LOOKBACK, LSTMbicis, STEP_MINUTES, TARGET_COLS

app = Flask(__name__)
CORS(app)  # Permite llamadas desde el frontend React

# Configurar MLflow una sola vez al iniciar la API.
setup_mlflow()


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

        # Cargar modelo y escaladores desde MLflow.
        cached = load_model_and_scalers(station_id, run_id)
        model = cached["model"]
        scaler_x = cached["scaler_x"]
        scaler_y = cached["scaler_y"]
        feature_cols = cached["feature_cols"]

        # Obtener datos históricos de la estación.
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

        # Predecir y desescalar.
        horizon_steps = [h // STEP_MINUTES for h in HORIZONTES_MIN]
        pred_scaled = model.predict(ultima_ventana, verbose=0)[0]
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
    app.run(host="0.0.0.0", port=5001, debug=True)
