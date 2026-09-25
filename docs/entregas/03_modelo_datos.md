# 🗂️ Modelo de Datos y Capa Gold

Este documento describe el diseño técnico del modelo de datos del proyecto **Bicing Cerca de Mí**: desde la capa **Bronze** (fuentes originales sin procesar), pasando por la capa **Silver** en MySQL (datos limpios y modelados) hasta la capa **Gold**, que expone los resultados de predicción a través de una **API** para el frontend React (desarrollado con Vite y gestionado con pnpm).

---

## 1. Arquitectura de capas

```
Bronze (fuentes)      Silver (MySQL)            Gold (analítico)
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

| Capa | Descripción | Ubicación / implementación |
|---|---|---|
| **Bronze** | Datos originales sin transformar: CSV mensuales del Ajuntament y respuesta JSON de Open-Meteo. | `data/informacion/`, `data/estado/`, `backend/scripts/silver/4.fetch_clima_bcn.py` |
| **Silver** | Datos limpios, validados y modelados en MySQL con PKs, FKs y tipos correctos. | Base de datos `Bicing` (`backend/scripts/silver/01_create_db.py`, `backend/scripts/silver/02_insert_informacion.py`, `backend/scripts/silver/03_insert_estado.py`) |
| **Gold** | Resultados de predicción de bicicletas y anclajes mediante series temporales con deep learning, a partir de MySQL y el clima. | API REST que expone predicciones en JSON; consumida por el frontend React. |

---

## 2. Capa Bronze (fuentes originales)

Esta capa contiene los datos tal cual se reciben. No se aplica ninguna transformación de negocio; únicamente se describen los esquemas originales.

### 2.1 Datos de estaciones (`data/informacion/`)

Archivos CSV mensuales con el prefijo `*_BicingNou_INFORMACIO.csv`. Cada archivo describe las estaciones existentes en ese mes.

| Campo | Tipo en origen | Descripción |
|---|---|---|
| `station_id` | entero | Identificador único de la estación. |
| `physical_configuration` | texto | Tipo de estación (`ELECTRICBIKESTATION`, etc.). |
| `lat` / `lon` | float | Coordenadas geográficas. |
| `address` | texto | Dirección o nombre de la calle. |
| `post_code` | texto | Código postal (se normaliza a 5 dígitos). |
| `capacity` | entero | Número total de anclajes. |
| `last_updated` | entero (epoch s) | Última actualización del registro. |

### 2.2 Datos de estado (`data/estado/`)

Archivos CSV mensuales con el prefijo `*_BicingNou_ESTACIONS.csv`. Cada fila es una instantánea del estado de una estación.

| Campo | Tipo en origen | Descripción |
|---|---|---|
| `station_id` | entero | Identificador de la estación. |
| `num_bikes_available` | entero | Bicis disponibles. |
| `num_bikes_available_types.mechanical` | entero | Bicis mecánicas disponibles. |
| `num_bikes_available_types.ebike` | entero | Bicis eléctricas disponibles. |
| `num_docks_available` | entero | Anclajes libres. |
| `is_installed` / `is_renting` / `is_returning` | entero | Flags operativos (no se cargan en el modelo actual). |
| `status` | texto | Estado operativo (`IN_SERVICE`, etc.). |
| `last_reported` | entero (epoch s) | Marca de tiempo de la instantánea. |

### 2.3 Datos meteorológicos (Open-Meteo)

El script `backend/scripts/silver/4.fetch_clima_bcn.py` consulta la API de Open-Meteo para Barcelona (lat=41.3851, lon=2.1734) en el rango 2021-01-01 a 2025-09-30.

| Campo generado | Tipo | Descripción |
|---|---|---|
| `date` | `str` | Fecha (`YYYY-MM-DD`). |
| `hour` | `int` | Hora (`HH`). |
| `is_holiday` | bool | `True` si la fecha es festivo en Cataluña. |
| `temperature_c` | float | Temperatura a 2 metros en °C. |
| `relative_humidity_2m` | float | Humedad relativa a 2 metros (%). |
| `rain` | float | Precipitación en forma de lluvia (mm). |
| `cloud_cover` | float | Cobertura de nubes (%). |
| `wind_speed_10m` | float | Velocidad del viento a 10 metros (km/h). |

---

## 3. Capa Silver: base de datos MySQL

La base de datos `Bicing` constituye la capa Silver. Aquí los datos ya han sido limpiados, tipados, deduplicados y relacionados mediante claves primarias y foráneas. Los scripts `02_insert_informacion.py` y `03_insert_estado.py` realizan la carga desde Bronze hasta esta capa.

La base de datos `Bicing` se crea con `backend/scripts/silver/01_create_db.py` con codificación `utf8mb4_unicode_ci`.

### 3.1 Tabla `informacion`

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

| Campo | Tipo | PK | Descripción |
|---|---|---|---|
| `station_id` | `INT(3)` | ✅ | Identificador único de estación. |
| `physical_configuration` | `VARCHAR(30)` | | Tipo de estación. |
| `latitud` | `FLOAT` | | Latitud (renombrado desde `lat`). |
| `longitud` | `FLOAT` | | Longitud (renombrado desde `lon`). |
| `address` | `VARCHAR(100)` | | Dirección. |
| `post_code` | `VARCHAR(5)` | | CP normalizado a 5 dígitos. |
| `capacity` | `INT(2)` | | Capacidad total de anclajes. |
| `last_update` | `TIMESTAMP` | | Fecha de última actualización (renombrado desde `last_updated`, convertido de epoch). |

### 3.2 Tabla `estado`

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

| Campo | Tipo | PK | Descripción |
|---|---|---|---|
| `station_id` | `INT(3)` | ✅ | Parte de la clave primaria; referencia a `informacion`. |
| `datetime` | `TIMESTAMP` | ✅ | Parte de la clave primaria; generado desde `last_reported` (epoch s). |
| `num_bikes_available` | `INT(2)` | | Bicis totales disponibles. |
| `num_bikes_available_mechanical` | `INT(2)` | | Bicis mecánicas disponibles. |
| `num_bikes_available_ebike` | `INT(2)` | | Bicis eléctricas disponibles. |
| `num_docks_available` | `INT(2)` | | Anclajes libres. |

> **Restricciones:** la clave primaria compuesta `(station_id, datetime)` impide duplicados de instantáneas. La FK garantiza que cada `station_id` de `estado` exista en `informacion`.

---

## 4. Pipeline Bronze → Silver (scripts de carga)

Los scripts de la carpeta `backend/scripts/silver/` leen los archivos CSV de la capa Bronze, aplican limpieza y normalización, e insertan el resultado en la capa Silver de MySQL.

### 4.1 `backend/scripts/silver/02_insert_informacion.py`

- Lectura con **Polars** probando codificaciones `utf8`, `windows-1252` y `utf8-lossy`.
- Selección de columnas presentes en cada CSV.
- Conversión de `station_id` a entero.
- Renombrado de `lat` / `lon` a `latitud` / `longitud`.
- Conversión de `last_updated` (epoch s) a `last_update` tipo `datetime`.
- Normalización de `post_code` a 5 dígitos con relleno de ceros.
- Deduplicación por `station_id` conservando el último registro.
- Inserción por lotes de 10.000 con `ON DUPLICATE KEY UPDATE` para mantener la información más reciente.

### 4.2 `backend/scripts/silver/03_insert_estado.py`

- Lectura por lotes con `pl.scan_csv().collect_batches()` (`chunk_size=200_000`) para reducir uso de memoria.
- Schema override a `Float64` en columnas numéricas y a `Utf8` para `status`, para evitar errores de parseo.
- Filtrado de registros donde `status == "IN_SERVICE"`.
- Renombrado de `num_bikes_available_types.mechanical` / `.ebike` y conversión de `last_reported` a `datetime`.
- Deduplicación dentro de cada lote por `(station_id, datetime)`.
- Inserción por lotes de 5.000 filas con `INSERT IGNORE` para evitar bloqueos por duplicados.

### 4.3 `backend/scripts/silver/4.fetch_clima_bcn.py`

- Consulta anual a `https://archive-api.open-meteo.com/v1/archive`.
- Variables: `temperature_2m`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`.
- Marca `is_holiday` usando el paquete `holidays` (Cataluña).
- Devuelve un `DataFrame` con una fila por hora.

---

## 5. Capa Gold — Feature engineering, entrenamiento y predicción

La capa Gold **no persiste resultados en tablas MySQL**, sino en el **Model Registry de MLflow**. Se compone de:

- `backend/scripts/gold/bikes.py`: construye el dataset de features por estación (SQL + Python) y lo une con el clima.
- `backend/scripts/lstm_model.py`: clase `LSTMbicis` que encapsula entrenamiento y predicción multi-horizonte.
- `backend/scripts/train_all_stations.py`: orquestador que entrena y registra un modelo por estación en MLflow bajo el nombre `est_{station_id}`.

Cada modelo registrado incluye, además del modelo Keras, los escaladores `scaler_x`, `scaler_y` y la lista `feature_cols` como artifacts, para que la API pueda replicar exactamente el preprocesamiento sin reentrenar.

El frontend React consume la información de estaciones y las predicciones a través de la API REST `backend/api/informacion_api.py` (puerto 5002).

### 5.1 `backend/scripts/gold/bikes.py` — construcción de features

La función `cargar_estado_station(station_id)` ejecuta una consulta SQL contra la tabla `estado` que ya genera, en el propio motor de MySQL:

| Campo generado | Descripción |
|---|---|
| `nbm`, `nbe` | Alias de `num_bikes_available_mechanical` / `_ebike`. |
| `nd` | Alias de `num_docks_available` (anclajes libres). |
| `lag_nbm`, `lag_nbe` | Valor de `nbm`/`nbe` en el instante anterior (`LAG` con ventana `ORDER BY datetime`). |
| `hour_sin`, `hour_cos` | Codificación cíclica de la hora del día (a partir de `hour + minute/60`). |
| `dow_sin`, `dow_cos` | Codificación cíclica del día de la semana. |
| `year_sin`, `year_cos` | Codificación cíclica del día del año (considera años bisiestos). |

La función `bicis(station_id)`:

1. Llama a `cargar_estado_station` y castea `datetime`.
2. Llama a `fetch_clima_barcelona()` (`backend/scripts/silver/4.fetch_clima_bcn.py`) para obtener el clima horario y el flag `is_holiday`.
3. Hace `merge` entre el estado (a resolución de 5 min) y el clima (a resolución horaria) usando `date` + `hour`.
4. Reindexa la serie a una frecuencia fija de 5 minutos (`asfreq` + forward-fill) para rellenar huecos temporales.
5. Añade la columna booleana `is_imputed`, que marca `True` en las filas generadas por el relleno (frente a las filas originales reales).

El resultado es un único `DataFrame`, indexado por `datetime`, con todas las features listas para el modelo.

### 5.2 `backend/scripts/lstm_model.py` — modelo LSTM multi-horizonte

La clase `LSTMbicis` encapsula todo el pipeline de entrenamiento y predicción:

```python
modelo = LSTMbicis(station_id=30)
modelo.entrenar_y_predecir()
# tras entrenar: modelo.model, modelo.scaler_x, modelo.scaler_y, modelo.df
# Idealmente, registrar a continuación en MLflow con train_all_stations.py
```

- **Targets** (`TARGET_COLS`): `nbm` y `nbe` (bicis mecánicas y eléctricas disponibles).
- **Horizontes de predicción** (`HORIZONTES_MIN`): 5 y 10 minutos vista, con pasos de 5 minutos (`STEP_MINUTES`).
- **Ventana de entrada** (`LOOKBACK`): 24 pasos pasados (2 horas) por muestra.
- **Features de entrada** (`preparar_datos`): variables temporales cíclicas, `lag_nbm`/`lag_nbe`, `nd`, variables meteorológicas (`temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`), `is_holiday` e `is_imputed`. Todas se escalan con `MinMaxScaler` (ajustado solo con el tramo de entrenamiento).
- **Arquitectura** (`construir_modelo`): `LSTM(64) → Dropout(0.2) → LSTM(32) → Dropout(0.2) → Dense(32, relu) → Dense(n_outputs, linear)`, compilada con `adam` / `mse`, métrica `mae`.
- **Entrenamiento**: split cronológico en **tres tramos disjuntos** train/val/test (80/10/10 por defecto, `val_frac`/`test_frac`), con `EarlyStopping` sobre `val_loss` monitorizado únicamente en el tramo de validación; el tramo de test nunca participa en el entrenamiento ni en la selección de pesos. *(Actualizado en `04_analisis_modelado.md`, sección 5: la versión inicial reutilizaba el tramo de test como `validation_data`, lo que introducía fuga de información en la métrica final; ver detalle y justificación de la corrección en esa entrega.)*
- **Post-procesado**: las predicciones se recortan a `>= 0` (`np.maximum(fila, 0)`), ya que `nbm`/`nbe` no pueden ser negativos.

### 5.3 `backend/scripts/train_all_stations.py` — orquestador MLflow

Entrena y registra un modelo por cada `station_id` encontrado en MySQL:

- Crea un run en MLflow con nombre `est_{station_id}`.
- Guarda hiperparámetros, métricas de test y predicciones de referencia.
- Serializa `scaler_x`, `scaler_y` y `feature_cols` como artifacts bajo la ruta `scalers/`.
- Registra el modelo Keras en el Model Registry con `registered_model_name="est_{station_id}"`.

Soporta dos modos:

```bash
python backend/scripts/train_all_stations.py              # entrena solo estaciones sin modelo
python backend/scripts/train_all_stations.py --reentrenar-todos  # fuerza reentrenamiento completo
```

### 5.4 API implementada

La API REST está implementada en `backend/api/informacion_api.py` (Flask, puerto 5002) y expone los endpoints consumidos por el frontend. Existe también una API alternativa standalone en `backend/api/bicis_pred_api.py` (puerto 5001).

#### `GET /api/informacion`

Devuelve el listado de estaciones que tienen un modelo registrado en MLflow, con `station_id`, `latitud`, `longitud`, `address`, `post_code` y `capacity`.

```json
{
  "1": { "latitud": 41.387015, "longitud": 2.170047, "address": "Plaça de Catalunya", "post_code": "08002", "capacity": 20 },
  "...": { ... }
}
```

#### `POST /api/predict`

Carga el modelo `est_{station_id}`, los escaladores y las columnas de features desde MLflow, prepara la última ventana de datos disponible y devuelve la predicción a 5 y 10 minutos.

**Cuerpo de la petición:**

```json
{ "station_id": 30 }
```

**Respuesta 200:**

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

> La API no reentrena el modelo en cada petición. Carga el modelo Keras y los escaladores desde MLflow; la primera predicción de una estación descarga los artifacts (~20-30 s) y las siguientes usan el cache en memoria del servidor, por lo que la respuesta pasa a ser casi inmediata.

### 5.5 Flujo de la capa Gold

```
Silver (MySQL: estado + informacion) ──┐
                                        ▼
                          gold/bikes.py: cargar_estado_station()
                          + merge con clima (Open-Meteo) + reindex 5min
                                        │
                                        ▼
                          lstm_model.py: LSTMbicis.entrenar_y_predecir()
                                        │
                                        ▼
              train_all_stations.py: registro en MLflow (est_{station_id})
                          + artifacts scaler_x / scaler_y / feature_cols
                                        │
                                        ▼
              API REST (backend/api/informacion_api.py): carga modelo desde MLflow
                                        │
                                        ▼
                    Predicción nbm / nbe a 5 y 10 min vista
                                        │
                                        ▼
                              Frontend React
```

### 5.6 Relación capa Gold con el resto

- `gold/bikes.py` consume `estado` e `informacion` (FK) de la capa Silver, y el clima de Open-Meteo.
- `lstm_model.py` consume el `DataFrame` de `bikes.py` y entrena/predice.
- `train_all_stations.py` registra cada modelo entrenado en MLflow bajo `est_{station_id}` junto con sus escaladores.
- `backend/api/informacion_api.py` carga el modelo, los escaladores y los datos históricos desde MLflow/MySQL para servir predicciones sin reentrenar.
- El frontend React consume los endpoints en `http://localhost:5002`.

### 5.7 Ejemplo de consumo desde React (actual)

```javascript
const API_URL = 'http://localhost:5002';

// Llamada POST a /api/predict
async function getPrediction(stationId) {
  const response = await fetch(`${API_URL}/api/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ station_id: stationId }),
  });
  if (!response.ok) throw new Error('Error al obtener la predicción');
  return response.json();
}
```

---

## 6. Diagrama entidad-relación (capa Silver)

```
┌─────────────────┐         ┌────────────────────┐
│   informacion   │         │       estado       │
│   (dimensión)   │         │      (hechos)      │
├─────────────────┤         ├────────────────────┤
│ PK station_id   │◄────────│ PK/FK station_id   │
│    latitud      │    1:N  │ PK datetime        │
│    longitud     │         │    num_bikes_...   │
│    capacity     │         │    num_docks_...   │
│    address      │         └────────────────────┘
│    post_code    │                   │
│    physical_... │                   │ N:1
└─────────────────┘                   ▼ (merge en memoria, no FK en MySQL)
                            ┌───────────────────────────┐
                            │           clima           │
                            │        (dimensión)        │
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

> `clima` no es una tabla de MySQL: es el `DataFrame` que devuelve `fetch_clima_barcelona()` y que `gold/bikes.py` une en memoria con `estado` (por `date` + `hour`).

---

## 7. Consideraciones técnicas

- **Codificación:** toda la base de datos usa `utf8mb4_unicode_ci` para soportar caracteres catalanes y espacios.
- **Batching:** las inserciones se hacen en lotes (10.000 para `informacion`, 5.000 para `estado`) para evitar problemas de memoria y `max_allowed_packet`.
- **Idempotencia:** `informacion` usa `ON DUPLICATE KEY UPDATE`; `estado` usa `INSERT IGNORE` para evitar bloqueos por duplicados.
- **Memoria:** el script `03_insert_estado.py` lee CSV en lotes con Polars (`scan_csv().collect_batches()`) para poder procesar los ~63 archivos sin cargarlos enteros en RAM.
- **Clima:** `backend/scripts/silver/4.fetch_clima_bcn.py` devuelve un DataFrame con `date`, `hour`, `temperature_c`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m` e `is_holiday`. El script `backend/scripts/gold/bikes.py` une este DataFrame con la tabla `estado` de MySQL a partir de `date` y `hour` para construir el dataset de entrenamiento de la capa Gold.
- **Credenciales:** el acceso a MySQL ya no está hardcodeado en los scripts. `backend/scripts/silver/db_config.py` centraliza la lectura de credenciales desde variables de entorno (cargadas con `python-dotenv` desde un archivo `.env` en la raíz, no versionado). Ver `.env.example` para la plantilla de variables (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`).
