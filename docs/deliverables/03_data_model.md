# 🗂️ Data Model and Gold Layer

This document describes the technical data model design of the **Bicing Near Me** project: from the **Bronze** layer (raw sources), through the **Silver** layer in MySQL (clean and modeled data), to the **Gold** layer, which exposes prediction results via an **API** for the React frontend (developed with Vite and managed with pnpm).

---

## 1. Layer architecture

```
Bronze (sources)      ETL → MySQL            Gold (analytical)
    │                        │                          │
    ├── data/informacion/    │   ┌──────────────┐       │
    │        CSV             │   │  informacion │       │
    │          │             │   └──────────────┘       │
    ├── data/estado/         │          │               │
    │        CSV             │          ▼               │
    │          │             │   ┌──────────────┐       │
    │          └────────────►│   │    estado    │       │
    │                        │   └──────────────┘       │
    └── Open-Meteo API       │          │               │
             JSON            │          ▼               │
                             │   ┌──────────────┐       │
                             │   │    clima     │       │
                             │   └──────────────┘       │
                             │                          │
                             └──────────────────────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │   API Gold   │
                                   │ predicciones │
                                   │   (DL/TS)    │
                                   └──────────────┘
```

| Layer | Description | Location / implementation |
|---|---|---|
| **Bronze** | Original untransformed data: monthly CSVs from the City Council and JSON response from Open-Meteo. | `data/informacion/`, `data/estado/`, `backend/pipelines/etl/04_fetch_clima_bcn.py` |
| **Silver** | Clean, validated, and modeled data in MySQL with PKs, FKs, and correct types. | `Bicing` database (`backend/pipelines/etl/01_create_db.py`, `backend/pipelines/etl/02_insert_informacion.py`, `backend/pipelines/etl/03_insert_estado.py`) |
| **Gold** | Prediction results for bicycles and docks using time series with deep learning, based on MySQL and weather data. | REST API that exposes predictions in JSON; consumed by the React frontend. |

---

## 2. Bronze layer (raw sources)

This layer contains the data exactly as received. No business transformation is applied; only the original schemas are described.

### 2.1 Station data (`data/informacion/`)

Monthly CSV files with the prefix `*_BicingNou_INFORMACIO.csv`. Each file describes the stations existing in that month.

| Field | Source type | Description |
|---|---|---|
| `station_id` | integer | Unique identifier of the station. |
| `physical_configuration` | text | Station type (`ELECTRICBIKESTATION`, etc.). |
| `lat` / `lon` | float | Geographic coordinates. |
| `address` | text | Street address or name. |
| `post_code` | text | Postal code (normalized to 5 digits). |
| `capacity` | integer | Total number of docks. |
| `last_updated` | integer (epoch s) | Last update of the record. |

### 2.2 Status data (`data/estado/`)

Monthly CSV files with the prefix `*_BicingNou_ESTACIONS.csv`. Each row is a snapshot of a station's status.

| Field | Source type | Description |
|---|---|---|
| `station_id` | integer | Station identifier. |
| `num_bikes_available` | integer | Available bikes. |
| `num_bikes_available_types.mechanical` | integer | Available mechanical bikes. |
| `num_bikes_available_types.ebike` | integer | Available electric bikes. |
| `num_docks_available` | integer | Free docks. |
| `is_installed` / `is_renting` / `is_returning` | integer | Operational flags (not loaded in the current model). |
| `status` | text | Operational status (`IN_SERVICE`, etc.). |
| `last_reported` | integer (epoch s) | Timestamp of the snapshot. |

### 2.3 Weather data (Open-Meteo)

The script `backend/pipelines/etl/04_fetch_clima_bcn.py` queries the Open-Meteo API for Barcelona (lat=41.3851, lon=2.1734) in the range 2021-01-01 to 2025-09-30.

| Generated field | Type | Description |
|---|---|---|
| `date` | `str` | Date (`YYYY-MM-DD`). |
| `hour` | `int` | Hour (`HH`). |
| `is_holiday` | bool | `True` if the date is a holiday in Catalonia. |
| `temperature_c` | float | Temperature at 2 meters in °C. |
| `relative_humidity_2m` | float | Relative humidity at 2 meters (%). |
| `rain` | float | Rainfall in mm. |
| `cloud_cover` | float | Cloud cover (%). |
| `wind_speed_10m` | float | Wind speed at 10 meters (km/h). |

---

## 3. Silver layer: MySQL database

The `Bicing` database constitutes the Silver layer. Here the data has been cleaned, typed, deduplicated, and related through primary and foreign keys. The scripts `02_insert_informacion.py` and `03_insert_estado.py` load the data from Bronze to this layer.

The `Bicing` database is created with `backend/pipelines/etl/01_create_db.py` using `utf8mb4_unicode_ci` encoding. Credentials are read from `.env` through `backend/core/db.py`.

### 3.1 `informacion` table

```sql
CREATE TABLE IF NOT EXISTS informacion (
    station_id INT(3) NOT NULL,
    physical_configuration VARCHAR(30),
    latitud FLOAT,
    longitud FLOAT,
    address VARCHAR(100),
    post_code VARCHAR(5),
    capacity INT(2),
    last_update TIMESTAMP,
    PRIMARY KEY (station_id)
);
```

| Field | Type | PK | Description |
|---|---|---|---|
| `station_id` | `INT(3)` | ✅ | Unique station identifier. |
| `physical_configuration` | `VARCHAR(30)` | | Station type. |
| `latitud` | `FLOAT` | | Latitude (renamed from `lat`). |
| `longitud` | `FLOAT` | | Longitude (renamed from `lon`). |
| `address` | `VARCHAR(100)` | | Address. |
| `post_code` | `VARCHAR(5)` | | Zip code normalized to 5 digits. |
| `capacity` | `INT(2)` | | Total dock capacity. |
| `last_update` | `TIMESTAMP` | | Last update date (renamed from `last_updated`, converted from epoch). |

### 3.2 `estado` table

```sql
CREATE TABLE IF NOT EXISTS estado (
    station_id INT(3) NOT NULL,
    num_bikes_available INT(2),
    num_bikes_available_mechanical INT(2),
    num_bikes_available_ebike INT(2),
    num_docks_available INT(2),
    datetime TIMESTAMP,
    PRIMARY KEY (station_id, datetime),
    CONSTRAINT fk_estado_informacion
        FOREIGN KEY (station_id) REFERENCES informacion(station_id)
);
```

| Field | Type | PK | Description |
|---|---|---|---|
| `station_id` | `INT(3)` | ✅ | Part of the primary key; references `informacion`. |
| `datetime` | `TIMESTAMP` | ✅ | Part of the primary key; generated from `last_reported` (epoch s). |
| `num_bikes_available` | `INT(2)` | | Total available bikes. |
| `num_bikes_available_mechanical` | `INT(2)` | | Available mechanical bikes. |
| `num_bikes_available_ebike` | `INT(2)` | | Available electric bikes. |
| `num_docks_available` | `INT(2)` | | Free docks. |

> **Constraints:** the composite primary key `(station_id, datetime)` prevents duplicate snapshots. The FK ensures that every `station_id` in `estado` exists in `informacion`.

---

## 4. Bronze → Silver pipeline (load scripts)

The scripts in the `backend/pipelines/etl/` folder read the CSV files from the Bronze layer, apply cleaning and normalization, and insert the result into the Silver layer of MySQL. Each one imports the connection configuration from `backend/core/db.py`.

### 4.1 `backend/pipelines/etl/02_insert_informacion.py`

- Reading with **Polars** trying `utf8`, `windows-1252`, and `utf8-lossy` encodings.
- Selection of columns present in each CSV.
- Conversion of `station_id` to integer.
- Renaming `lat` / `lon` to `latitud` / `longitud`.
- Conversion of `last_updated` (epoch s) to `last_update` datetime type.
- Normalization of `post_code` to 5 digits with zero padding.
- Deduplication by `station_id` keeping the last record.
- Batch insertion of 10,000 with `ON DUPLICATE KEY UPDATE` to keep the most recent information.

### 4.2 `backend/pipelines/etl/03_insert_estado.py`

- Reading in batches with `pl.scan_csv().collect_batches()` (`chunk_size=200_000`) to reduce memory usage.
- Schema override to `Float64` in numeric columns and `Utf8` for `status`, to avoid parsing errors.
- Filtering records where `status == "IN_SERVICE"`.
- Renaming `num_bikes_available_types.mechanical` / `.ebike` and converting `last_reported` to datetime.
- Deduplication within each batch by `(station_id, datetime)`.
- Batch insertion of 5,000 rows with `INSERT IGNORE` to avoid blocking due to duplicates.

### 4.3 `backend/pipelines/etl/04_fetch_clima_bcn.py`

- Annual query to `https://archive-api.open-meteo.com/v1/archive`.
- Variables: `temperature_2m`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`.
- `is_holiday` flag using the `holidays` package (Catalonia).
- Returns a DataFrame with one row per hour.

---

## 5. Gold layer — Feature engineering, training, and prediction

The Gold layer **does not persist results in MySQL tables**, but in the **MLflow Model Registry**. The shared logic between training and inference now lives in `backend/core` to avoid coupling between the API, ETL scripts, and notebooks:

- `backend/core/features.py`: builds the feature dataset per station (SQL + Python) and joins it with weather.
- `backend/core/model.py`: `LSTMbicis` class that encapsulates multi-horizon training and prediction.
- `backend/core/mlflow_client.py`: run lookup, scaler download, and cached model loading used by the API.
- `backend/pipelines/ml/train_all_stations.py`: orchestrator that trains and registers one model per station in MLflow under the name `est_{station_id}`.

Each registered model includes, in addition to the Keras model, the `scaler_x`, `scaler_y`, and `feature_cols` scalers as artifacts, so that the API can replicate exactly the preprocessing without retraining.

The React frontend consumes station information and predictions through the REST API `backend/api/informacion_api.py` (port 5002). The API delegates to `backend/core/mlflow_client.py` the search for the run and the cached loading of models/scalers.

### 5.1 `backend/core/features.py` — feature construction

The function `cargar_estado_station(station_id)` executes an SQL query against the `estado` table that already generates, within the MySQL engine itself:

| Generated field | Description |
|---|---|
| `nbm`, `nbe` | Aliases of `num_bikes_available_mechanical` / `_ebike`. |
| `nd` | Alias of `num_docks_available` (free docks). |
| `lag_nbm`, `lag_nbe` | Value of `nbm`/`nbe` at the previous instant (`LAG` window `ORDER BY datetime`). |
| `hour_sin`, `hour_cos` | Cyclic encoding of the hour of day (from `hour + minute/60`). |
| `dow_sin`, `dow_cos` | Cyclic encoding of the day of the week. |
| `year_sin`, `year_cos` | Cyclic encoding of the day of the year (leap-year aware). |

The function `bicis(station_id)`:

1. Calls `cargar_estado_station` and casts `datetime`.
2. Calls `fetch_clima_barcelona()` (`backend/pipelines/etl/04_fetch_clima_bcn.py`) to get hourly weather and the `is_holiday` flag.
3. Performs a `merge` between status (5-min resolution) and weather (hourly resolution) using `date` + `hour`.
4. Reindexes the series to a fixed 5-minute frequency (`asfreq` + forward-fill) to fill temporal gaps.
5. Adds the boolean column `is_imputed`, which marks `True` for rows generated by the fill (as opposed to original real rows).

The result is a single `DataFrame`, indexed by `datetime`, with all features ready for the model.

### 5.2 `backend/core/model.py` — multi-horizon LSTM model

The `LSTMbicis` class (now in `backend/core/model.py`) encapsulates the entire training and prediction pipeline:

```python
from backend.core.model import LSTMbicis

modelo = LSTMbicis(station_id=30)
modelo.entrenar_y_predecir()
# after training: modelo.model, modelo.scaler_x, modelo.scaler_y, modelo.df
# Ideally, register afterwards with train_all_stations.py
```

- **Targets** (`TARGET_COLS`): `nbm` and `nbe` (available mechanical and electric bikes).
- **Prediction horizons** (`HORIZONTES_MIN`): 5 and 10 minutes ahead, with 5-minute steps (`STEP_MINUTES`).
- **Input window** (`LOOKBACK`): 24 past steps (2 hours) per sample.
- **Input features** (`preparar_datos`, in `backend/core/model.py`): cyclic temporal variables, `lag_nbm`/`lag_nbe`, `nd`, weather variables (`temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`), `is_holiday`, and `is_imputed`. All are scaled with `MinMaxScaler` (fitted only on the training segment).
- **Architecture** (`construir_modelo`): `LSTM(64) → Dropout(0.2) → LSTM(32) → Dropout(0.2) → Dense(32, relu) → Dense(n_outputs, linear)`, compiled with `adam` / `mse`, metric `mae`.
- **Training**: chronological split into **three disjoint segments** train/val/test (80/10/10 by default, `val_frac`/`test_frac`), with `EarlyStopping` on `val_loss` monitored only on the validation segment; the test segment never participates in training or weight selection. *(Updated in `04_modeling_analysis.md`, section 5: the initial version reused the test segment as `validation_data`, which introduced information leakage into the final metric; see that deliverable for details and justification of the correction.)*
- **Post-processing**: predictions are clipped to `>= 0` (`np.maximum(fila, 0)`), since `nbm`/`nbe` cannot be negative.

### 5.3 `backend/pipelines/ml/train_all_stations.py` — MLflow orchestrator

Trains and registers one model for each `station_id` found in MySQL:

- Creates an MLflow run named `est_{station_id}`.
- Saves hyperparameters, test metrics, and reference predictions.
- Serializes `scaler_x`, `scaler_y`, and `feature_cols` as artifacts under the `scalers/` path.
- Registers the Keras model in the Model Registry with `registered_model_name="est_{station_id}"`.

Two modes are supported:

```bash
python backend/pipelines/ml/train_all_stations.py              # trains only stations without a model
python backend/pipelines/ml/train_all_stations.py --reentrenar-todos  # forces full retraining
```

### 5.4 Implemented API

The REST API is implemented in `backend/api/informacion_api.py` (Flask, port 5002) and exposes the endpoints consumed by the frontend. There is also a standalone alternative API in `backend/api/bicis_pred_api.py` (port 5001).

#### `GET /api/informacion`

Returns the list of stations that have a model registered in MLflow, with `station_id`, `latitud`, `longitud`, `address`, `post_code`, and `capacity`.

```json
{
  "1": { "latitud": 41.387015, "longitud": 2.170047, "address": "Plaça de Catalunya", "post_code": "08002", "capacity": 20 },
  "...": { ... }
}
```

#### `POST /api/predict`

Loads the model `est_{station_id}`, the scalers, and the feature columns from MLflow, prepares the last available data window, and returns the prediction at 5 and 10 minutes.

**Request body:**

```json
{ "station_id": 30 }
```

**200 response:**

```json
{
  "station_id": 30,
  "last_timestamp": "2025-09-30T21:51:23",
  "predictions": [
    { "horizon_minutes": 5,  "timestamp": "...", "nbm": 11.24, "nbe": 0.44 },
    { "horizon_minutes": 10, "timestamp": "...", "nbm": 11.27, "nbe": 0.61 }
  ]
}
```

> The API does not retrain the model on each request. It loads the Keras model and scalers from MLflow; the first prediction for a station downloads the artifacts (~20-30 s) and subsequent ones use the server's in-memory cache, so the response becomes almost immediate.

### 5.5 Gold layer flow

```
Silver (MySQL: estado + informacion) ──┐
                                        ▼
                          core/features.py: cargar_estado_station()
                          + merge with weather (Open-Meteo) + 5min reindex
                                        │
                                        ▼
                          core/model.py: LSTMbicis.entrenar_y_predecir()
                                        │
                                        ▼
              train_all_stations.py: register in MLflow (est_{station_id})
                          + scaler_x / scaler_y / feature_cols artifacts
                                        │
                                        ▼
              API REST (backend/api/informacion_api.py): load model from MLflow
                                        │
                                        ▼
                    Prediction nbm / nbe at 5 and 10 minutes ahead
                                        │
                                        ▼
                              Frontend React
```

### 5.6 Relationship of the Gold layer with the rest

- `backend/core/features.py` consumes `estado` and `informacion` (FK) from the Silver layer, and weather from Open-Meteo.
- `backend/core/model.py` consumes the `DataFrame` from `backend/core/features.py` and trains/predicts.
- `backend/pipelines/ml/train_all_stations.py` registers each trained model in MLflow under `est_{station_id}` together with its scalers.
- `backend/api/informacion_api.py` exposes HTTP endpoints and delegates to `backend/core/mlflow_client.py` and `backend/core/model.py` to load the model, scalers, and historical data from MLflow/MySQL and serve predictions without retraining.
- The React frontend consumes the endpoints at `http://localhost:5002`.

### 5.7 Example consumption from React (current)

```javascript
const API_URL = 'http://localhost:5002';

// POST call to /api/predict
async function getPrediction(stationId) {
  const response = await fetch(`${API_URL}/api/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ station_id: stationId }),
  });
  if (!response.ok) throw new Error('Error obtaining prediction');
  return response.json();
}
```

---

## 6. Entity-relationship diagram (Silver layer)

```
┌─────────────────┐         ┌────────────────────┐
│   informacion   │         │       estado       │
│   (dimension)   │         │      (facts)       │
├─────────────────┤         ├────────────────────┤
│ PK station_id   │◄────────│ PK/FK station_id   │
│    latitud      │    1:N  │ PK datetime        │
│    longitud     │         │    num_bikes_...   │
│    capacity     │         │    num_docks_...   │
│    address      │         └────────────────────┘
│    post_code    │                   │
│    physical_... │                   │ N:1
└─────────────────┘                   ▼ (merge in memory, no FK in MySQL)
                            ┌───────────────────────────┐
                            │           clima           │
                            │        (dimension)        │
                            ├───────────────────────────┤
                            │ PK date + hour            │
                            │    temperature_c          │
                            │    relative_humidity_2m   │
                            │    rain                   │
                            │    cloud_cover            │
                            │    wind_speed_10m         │
                            │    is_holiday             │
                            └───────────────────────────┘
```

> `clima` is not a MySQL table: it is the DataFrame returned by `fetch_clima_barcelona()` and joined in memory by `backend/core/features.py` with `estado` (by `date` + `hour`).

---

## 7. Technical considerations

- **Encoding:** the entire database uses `utf8mb4_unicode_ci` to support Catalan characters and spaces.
- **Batching:** insertions are done in batches (10,000 for `informacion`, 5,000 for `estado`) to avoid memory and `max_allowed_packet` problems.
- **Idempotency:** `informacion` uses `ON DUPLICATE KEY UPDATE`; `estado` uses `INSERT IGNORE` to avoid blocking due to duplicates.
- **Memory:** the script `03_insert_estado.py` reads CSVs in batches with Polars (`scan_csv().collect_batches()`) to process the ~63 files without loading them entirely into RAM.
- **Weather:** `backend/pipelines/etl/04_fetch_clima_bcn.py` returns a DataFrame with `date`, `hour`, `temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`, and `is_holiday`. The module `backend/core/features.py` joins this DataFrame with the `estado` table from MySQL by `date` and `hour` to build the Gold layer training dataset.
- **Credentials:** MySQL access is no longer hardcoded in the pipelines. `backend/core/db.py` centralizes credential reading from environment variables (loaded with `python-dotenv` from a `.env` file in the root, not versioned). See `.env.example` for the variable template (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`).
- **Layer architecture:** the `backend/api` layer only exposes HTTP endpoints and delegates MLflow, feature, and model logic to `backend/core`. The ETL pipelines (`backend/pipelines`) use `backend/core` as a shared library; this avoids code duplication between training and inference and eliminates scattered `sys.path.insert` calls.
