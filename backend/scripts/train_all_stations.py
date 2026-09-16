"""
Orquestador MLflow: entrena y registra un modelo LSTM por cada estación
de Bicing disponible en la tabla `informacion`.

Cada modelo queda registrado en MLflow con el nombre "est_{station_id}"
(p.ej. "est_1", "est_42", "est_510").

Uso:
    python train_all_stations.py

Requisitos:
    - Servidor MLflow en ejecución (por defecto http://localhost:5000).
      Inícialo con:  mlflow server --host 0.0.0.0 --port 5000
    - Variables de entorno de MySQL configuradas en .env (ver db_config.py).
    - Dependencias: mlflow, tensorflow, scikit-learn, pandas, sqlalchemy, etc.
"""

import sys
import time
import traceback
from pathlib import Path

import mlflow
import mlflow.tensorflow
import pandas as pd
from sqlalchemy import create_engine

# Añadir al path la carpeta scripts para importar lstm_model y silver
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "silver"))

from lstm_model import LSTMbicis, LOOKBACK, HORIZONTES_MIN, STEP_MINUTES, TARGET_COLS
from db_config import get_sqlalchemy_url

# Configuración de MLflow
MLFLOW_TRACKING_URI = "http://localhost:5000"
MLFLOW_EXPERIMENT_NAME = "bicing_lstm_predictions"


def obtener_station_ids():
    """Consulta los IDs de estación desde la tabla `informacion`."""
    query = """
        SELECT station_id
        FROM informacion
        WHERE station_id <> 588
        ORDER BY station_id
    """
    engine = create_engine(get_sqlalchemy_url())
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df["station_id"].astype(int).tolist()


def entrenar_y_registrar(station_id: int):
    """Entrena el modelo LSTM para una estación y lo registra en MLflow.

    - Crea un run en MLflow con los parámetros e hiperparámetros.
    - Loguea las métricas de test (loss/mse y mae).
    - Registra el modelo Keras en el Model Registry como "est_{station_id}".
    """
    model_name = f"est_{station_id}"

    with mlflow.start_run(run_name=model_name):
        # Loguear parámetros del modelo
        mlflow.log_param("station_id", station_id)
        mlflow.log_param("lookback", LOOKBACK)
        mlflow.log_param("step_minutes", STEP_MINUTES)
        mlflow.log_param("horizontes_min", str(HORIZONTES_MIN))
        mlflow.log_param("target_cols", str(TARGET_COLS))

        # Crear instancia y entrenar
        modelo = LSTMbicis(station_id=station_id)
        modelo.entrenar_y_predecir()

        # Loguear métricas de test
        loss, mae = modelo.model.evaluate(
            # Re-evaluar sobre el último bloque para obtener las métricas.
            # Como entrenar_y_predecir() ya evaluó, usamos las métricas
            # del propio modelo sobre la última ventana completa.
            *_obtener_test_data(modelo),
            verbose=0,
        )
        mlflow.log_metric("test_loss_mse", loss)
        mlflow.log_metric("test_mae", mae)

        # Loguear predicciones como parámetros para referencia rápida
        if modelo.predictions:
            for pred in modelo.predictions:
                h = pred["horizon_minutes"]
                mlflow.log_metric(f"pred_nbm_{h}min", pred["nbm"])
                mlflow.log_metric(f"pred_nbe_{h}min", pred["nbe"])
            mlflow.log_param("last_timestamp", modelo.last_timestamp)

        # Registrar el modelo en el Model Registry
        mlflow.tensorflow.log_model(
            model=modelo.model,
            artifact_path="model",
            registered_model_name=model_name,
        )

    return loss, mae


def _obtener_test_data(modelo: LSTMbicis):
    """Reconstruye X_test e y_test a partir del estado interno del modelo
    ya entrenado, replicando la misma lógica de split de entrenar_y_predecir().
    """
    df = modelo.df
    df_features, _ = modelo.preparar_datos(df)
    df_targets = df[modelo.target_cols].astype(float)

    horizon_steps = [h // modelo.step_minutes for h in modelo.horizontes_min]
    min_block = max(horizon_steps) + modelo.lookback + 1

    n_total = len(df_features)
    n_test = max(int(n_total * modelo.test_frac), min_block)
    n_val = max(int(n_total * modelo.val_frac), min_block)
    n_train = n_total - n_val - n_test

    features_scaled = modelo.scaler_x.transform(df_features)
    targets_scaled = modelo.scaler_y.transform(df_targets)

    X, y = LSTMbicis.construir_secuencias(
        features_scaled, targets_scaled, modelo.lookback, horizon_steps
    )

    split_val_test = n_train + n_val - modelo.lookback
    X_test = X[split_val_test:]
    y_test = y[split_val_test:]

    return X_test, y_test


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    print("Obteniendo lista de estaciones...")
    station_ids = obtener_station_ids()
    total = len(station_ids)
    print(f"Estaciones encontradas: {total}\n")

    exitosas = 0
    fallidas = []

    for idx, station_id in enumerate(station_ids, start=1):
        print(f"[{idx}/{total}] Entrenando estación {station_id} (est_{station_id})...")
        t0 = time.time()

        try:
            loss, mae = entrenar_y_registrar(station_id)
            elapsed = time.time() - t0
            print(
                f"  -> OK en {elapsed:.1f}s | "
                f"test_mse={loss:.4f} | test_mae={mae:.4f}"
            )
            exitosas += 1
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  -> ERROR en {elapsed:.1f}s: {e}")
            traceback.print_exc()
            fallidas.append(station_id)

    print(f"\n{'='*60}")
    print(f"Resumen: {exitosas}/{total} modelos registrados correctamente.")
    if fallidas:
        print(f"Estaciones con error ({len(fallidas)}): {fallidas}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
