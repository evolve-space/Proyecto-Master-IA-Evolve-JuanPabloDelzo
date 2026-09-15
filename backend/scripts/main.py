import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping

# Pasos de 5 minutos entre cada fila (frecuencia fijada por bicis() en bikes.py).
STEP_MINUTES = 5
# Horizontes de predicción solicitados: 5 y 10 minutos vista.
HORIZONTES_MIN = (5, 10)
LOOKBACK = 24  # nº de pasos pasados (24 * 5min = 2 horas) usados como entrada de la LSTM
TARGET_COLS = ["nbm", "nbe"]


class LSTMbicis:
    """Encapsula todo el pipeline de carga, preparación, entrenamiento y
    predicción de disponibilidad de bicis (mecánicas y eléctricas) mediante
    una red LSTM multi-horizonte.

    Uso:
        modelo = LSTMbicis(station_id=30)
        modelo.entrenar_y_predecir()
        # Tras entrenar, quedan disponibles:
        modelo.model, modelo.scaler_x, modelo.scaler_y, modelo.df
    """

    def __init__(
        self,
        station_id: int,
        step_minutes: int = STEP_MINUTES,
        horizontes_min=HORIZONTES_MIN,
        lookback: int = LOOKBACK,
        target_cols=TARGET_COLS,
        val_frac: float = 0.1,
        test_frac: float = 0.1,
    ):
        self.station_id = station_id
        self.step_minutes = step_minutes
        self.horizontes_min = horizontes_min
        self.lookback = lookback
        self.target_cols = target_cols
        # Tres tramos temporales independientes: train (resto), val (early
        # stopping / selección de modelo) y test (evaluación final, nunca
        # visto durante el entrenamiento ni la selección de hiperparámetros).
        self.val_frac = val_frac
        self.test_frac = test_frac

        self.df = None
        self.feature_cols = None
        self.model = None
        self.scaler_x = None
        self.scaler_y = None
        self.predictions = None
        self.last_timestamp = None

    @staticmethod
    def _import_bicis():
        """Importa dinámicamente la función `bicis` desde backend/scripts/gold/bikes.py."""
        module_path = Path(__file__).resolve().parent / "gold" / "bikes.py"
        spec = importlib.util.spec_from_file_location("bikes", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["bikes"] = module
        spec.loader.exec_module(module)
        return module.bicis

    def preparar_datos(self, df: pd.DataFrame):
        """Codifica variables categóricas/booleanas y separa features y targets.

        Returns:
            df_features: DataFrame con las columnas de entrada ya codificadas.
            feature_cols: nombres finales de columnas de entrada (incluye
                las dummies de `condicion`).
        """
        df = df.copy()
        #Tranformando boleanas  positivos (1) y negativos (0)
        df = df.assign(
            is_imputed=df.is_imputed.astype(int),
            is_holiday=df.is_holiday.astype(int)
        )
        
        time_cols = [
            "hour_sin",
            "hour_cos",
            "dow_sin",
            "dow_cos",
            "year_sin",
            "year_cos",
        ]
        lag_cols = ["lag_nbm", "lag_nbe"]
        weather_cols = [
            "temperature_c",
            "relative_humidity_2m",
            "rain",
            "cloud_cover",
            "wind_speed_10m",
        ]

        df_features = df[
            time_cols + lag_cols + weather_cols + ["is_holiday", "is_imputed"]
        ].astype(float)

        df_features = df_features.ffill().bfill()

        feature_cols = list(df_features.columns)
        return df_features, feature_cols

    @staticmethod
    def construir_secuencias(features: np.ndarray, targets: np.ndarray, lookback: int, horizon_steps):
        """Construye secuencias (X) y salidas multi-horizonte (y) para la LSTM.

        Para cada instante `i`, `X` contiene la ventana `features[i-lookback:i]`
        e `y` contiene los valores de `targets` en `i + h - 1` para cada `h` en
        `horizon_steps` (h=1 -> 5 min vista, h=2 -> 10 min vista).
        """
        n_samples = len(features)
        max_h = max(horizon_steps)

        X, y = [], []
        for i in range(lookback, n_samples - max_h + 1):
            X.append(features[i - lookback:i])
            fila_y = []
            for h in horizon_steps:
                fila_y.append(targets[i + h - 1])
            y.append(np.concatenate(fila_y))

        return np.array(X), np.array(y)

    @staticmethod
    def construir_modelo(input_shape, n_outputs):
        model = Sequential([
            Input(shape=input_shape),
            LSTM(64, activation="tanh", return_sequences=True),
            Dropout(0.2),
            LSTM(32, activation="tanh", return_sequences=False),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(n_outputs, activation="linear"),
        ])
        model.compile(optimizer="adam", loss="mse", metrics=["mae"])
        return model

    def entrenar_y_predecir(self):
        bicis = self._import_bicis()
        df = bicis(self.station_id)
        self.df = df

        df_features, feature_cols = self.preparar_datos(df)
        self.feature_cols = feature_cols
        df_targets = df[self.target_cols].astype(float)

        horizon_steps = [h // self.step_minutes for h in self.horizontes_min]
        min_block = max(horizon_steps) + self.lookback + 1

        # Tres tramos temporales *disjuntos y en orden cronológico*:
        # train -> val -> test. El bloque de test queda completamente al
        # margen del entrenamiento y de la selección de modelo (EarlyStopping
        # usa únicamente el bloque de validación), por lo que la métrica
        # final sobre test es una estimación independiente del error.
        n_total = len(df_features)
        n_test = max(int(n_total * self.test_frac), min_block)
        n_val = max(int(n_total * self.val_frac), min_block)
        n_train = n_total - n_val - n_test
        if n_train <= min_block:
            raise ValueError(
                "Serie demasiado corta para separar train/val/test con el "
                f"lookback y horizonte actuales (n_total={n_total})."
            )

        # El escalado se ajusta SOLO con el tramo de entrenamiento, para que
        # ni la validación ni el test filtren información hacia el fit.
        scaler_x = MinMaxScaler()
        scaler_y = MinMaxScaler()
        scaler_x.fit(df_features.iloc[:n_train])
        scaler_y.fit(df_targets.iloc[:n_train])
        self.scaler_x = scaler_x
        self.scaler_y = scaler_y

        features_scaled = scaler_x.transform(df_features)
        targets_scaled = scaler_y.transform(df_targets)

        X, y = self.construir_secuencias(features_scaled, targets_scaled, self.lookback, horizon_steps)

        split_train_val = n_train - self.lookback
        split_val_test = n_train + n_val - self.lookback
        X_train, X_val, X_test = (
            X[:split_train_val],
            X[split_train_val:split_val_test],
            X[split_val_test:],
        )
        y_train, y_val, y_test = (
            y[:split_train_val],
            y[split_train_val:split_val_test],
            y[split_val_test:],
        )

        n_outputs = y.shape[1]
        model = self.construir_modelo(input_shape=(self.lookback, X.shape[2]), n_outputs=n_outputs)
        self.model = model

        early_stopping = EarlyStopping(
            monitor="val_loss", patience=5, restore_best_weights=True
        )
        model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=2,
            batch_size=64,
            callbacks=[early_stopping],
            verbose=1,
        )

        # Test: bloque cronológicamente posterior, no usado ni en el fit ni
        # en el EarlyStopping -> métrica de error independiente.
        loss, mae = model.evaluate(X_test, y_test, verbose=0)
        print(f"\nEvaluación en test -> loss(mse): {loss:.4f} | mae: {mae:.4f}")

        # Predicción a partir de la última ventana disponible (último valor de
        # tiempo en el índice de `df`).
        ultima_ventana = features_scaled[-self.lookback:].reshape(1, self.lookback, X.shape[2])
        pred_scaled = model.predict(ultima_ventana, verbose=0)[0]

        # pred_scaled = [mech_5min, mech_10min, ebike_5min, ebike_10min]
        n_targets = len(self.target_cols)
        n_horizons = len(horizon_steps)
        pred_matrix_scaled = pred_scaled.reshape(n_horizons, n_targets)
        pred_matrix = scaler_y.inverse_transform(pred_matrix_scaled)

        ultimo_timestamp = df.index[-1]
        self.last_timestamp = ultimo_timestamp.isoformat()
        self.predictions = []
        print(f"\nÚltimo timestamp disponible: {ultimo_timestamp}")
        for h_min, fila in zip(self.horizontes_min, pred_matrix):
            pred_dt = ultimo_timestamp + pd.Timedelta(minutes=h_min)
            mech_pred, ebike_pred = np.maximum(fila, 0)
            mech_pred = float(mech_pred)
            ebike_pred = float(ebike_pred)
            self.predictions.append(
                {
                    "horizon_minutes": int(h_min),
                    "timestamp": pred_dt.isoformat(),
                    "nbm": mech_pred,
                    "nbe": ebike_pred,
                }
            )
            print(
                f"+{h_min} min ({pred_dt}): "
                f"nbm≈{mech_pred:.2f} | nbe≈{ebike_pred:.2f}"
            )

        return model, scaler_x, scaler_y


if __name__ == "__main__":
    modelo = LSTMbicis(station_id=30)
    modelo.entrenar_y_predecir()
