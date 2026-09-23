# 📦 Datos Necesarios para el Proyecto

Para predecir la disponibilidad de bicicletas y anclajes en las estaciones, se requerirán dos tipos de datos bien diferenciados. Dichos datos están disponibles en la página web del ayuntamiento de Barcelona y se han descargado en la carpeta `data/`:  

- [Información de las estaciones Bicing](https://opendata-ajuntament.barcelona.cat/data/es/dataset/informacio-estacions-bicing)
- [Estado de las estaciones Bicing](https://opendata-ajuntament.barcelona.cat/data/es/dataset/estat-estacions-bicing)

Además, se enriquece el dataset con datos meteorológicos históricos de Barcelona obtenidos de la API de **Open-Meteo** (`backend/scripts/silver/4.fetch_clima_bcn.py`).

Para preparar el dataset de modelado, se ha añadido el script `backend/scripts/gold/bikes.py`, que carga el histórico de una estación desde MySQL (con lags y variables temporales cíclicas ya calculadas en SQL) y lo une con el DataFrame del clima.

---

## ¿Qué datos tenemos?

```
data/
├── estado/                     ← Historial temporal de cada estación (CSV mensuales)
│   ├── 2021_01_Gener_BicingNou_ESTACIONS.csv
│   ├── 2021_02_Febrer_BicingNou_ESTACIONS.csv
│   ├── ...
│   └── 2025_09_Setembre_BicingNou_ESTACIONS.csv
│
└── informacion/                ← Características de cada estación (CSV mensuales)
    ├── 2021_01_Gener_BicingNou_INFORMACIO.csv
    ├── 2021_02_Febrer_BicingNou_INFORMACIO.csv
    ├── ...
    └── 2025_09_Setembre_BicingNou_INFORMACIO.csv
```

---

## 1. 🕐 Estado de las Estaciones — Datos Temporales

Son archivos mensuales en formato `.csv` ubicados en `data/estado/`, organizados por año y mes (desde enero de **2021** hasta septiembre de **2025**). Cada archivo captura el **estado en tiempo real** de todas las estaciones, registrando múltiples instantáneas a lo largo del mes.

**Nombre de archivo de ejemplo:**
```
data/estado/2024_03_Marc_BicingNou_ESTACIONS.csv
```

### ¿Qué contiene cada registro?

| Campo | Descripción |
|---|---|
| `station_id` | Identificador único de la estación |
| `num_bikes_available` | Total de bicis disponibles para coger |
| `num_bikes_available_types.mechanical` | Bicis mecánicas disponibles |
| `num_bikes_available_types.ebike` | Bicis eléctricas disponibles |
| `num_docks_available` | Anclajes libres para devolver |
| `is_installed` | Si la estación está instalada (1 = sí) |
| `is_renting` | Si está activa para alquiler (1 = sí) |
| `is_returning` | Si acepta devoluciones (1 = sí) |
| `status` | Estado operativo (`IN_SERVICE`, etc.) |
| `last_reported` | Marca de tiempo del último reporte (Unix) |

### ¿Cómo se ve la dimensión temporal?

```
Tiempo ──────────────────────────────────────────────────────────►

  Ene    Dic    Ene    Dic    Ene    Dic    Ene   Dic    Ene    Sep
 2021   2021   2022   2022   2023   2023   2024   2024  2025   2025
  │      │      │      │      │      │      │      │      │      │
  ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
 [====2021====][====2022====][====2023====][====2024====][====2025====] ...
```

> 📅 En total: **63 archivos mensuales** en `data/estado/`, cubriendo **5 años** de historial.

---

## 2. 📍 Información de las Estaciones — Datos Estáticos

Archivos `.csv` mensuales en `data/informacion/` con las **características fijas** de cada estación (aunque pueden existir pequeñas variaciones mensuales, como cambios de capacidad o dirección). Describen dónde está cada estación y cómo es.

**Archivo de ejemplo:** `data/informacion/2024_03_Marc_BicingNou_INFORMACIO.csv`

### ¿Qué contiene?

| Campo | Descripción |
|---|---|
| `station_id` | Identificador único (clave de unión con el otro dataset) |
| `name` | Nombre o dirección de la estación |
| `lat` / `lon` | Coordenadas geográficas |
| `altitude` | Altitud en metros |
| `address` | Dirección postal |
| `capacity` | Número total de anclajes de la estación |
| `is_charging_station` | Si tiene carga para e-bikes |
| `physical_configuration` | Tipo de estación (ej. `ELECTRICBIKESTATION`) |

### ¿Cómo se relacionan los dos datasets?

```
Informacion_estaciones.csv          Estado estaciones (mensual)
┌──────────────────────┐            ┌────────────────────────────┐
│ station_id  │ lat/lon│            │ station_id │ num_bikes_... │
│ station_id  │ capacit│  ◄──────►  │ station_id │ num_docks_... │
│ station_id  │ address│  station_id│ station_id │ last_reported │
└──────────────────────┘            └────────────────────────────┘
       (dónde está y cómo es)              (cómo está en cada momento)
```

---

## 3. 🌤️ Datos Meteorológicos — Open-Meteo

Para enriquecer el modelo y analizar la relación entre el clima y el uso de Bicing, se descargan datos horarios de Barcelona mediante la API de **Open-Meteo** (`backend/scripts/silver/4.fetch_clima_bcn.py`).

- **Coordenadas:** latitud `41.3851`, longitud `2.1734` (Barcelona)
- **Período:** `2021-01-01` a `2025-09-30`
- **Variables horarias:** `temperature_2m`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`
- **Zona horaria:** `Europe/Madrid`

**Campos que genera el script:**

| Campo | Descripción |
|---|---|
| `date` | Fecha del registro (`YYYY-MM-DD`) |
| `hour` | Hora del registro (`HH`) |
| `is_holiday` | `True` si la fecha es festivo en Cataluña, usando el paquete `holidays` |
| `temperature_c` | Temperatura a 2 metros en grados Celsius |
| `relative_humidity_2m` | Humedad relativa a 2 metros (%) |
| `rain` | Precipitación en forma de lluvia (mm) |
| `cloud_cover` | Cobertura de nubes (%) |
| `wind_speed_10m` | Velocidad del viento a 10 metros (km/h) |


**Script de unión con datos históricos:** `backend/scripts/gold/bikes.py`

- Lee la tabla `estado` de MySQL filtrando por `station_id`, calculando en SQL los lags (`lag_nbm`, `lag_nbe`) y las variables temporales cíclicas (`hour_sin/cos`, `dow_sin/cos`, `year_sin/cos`).
- Genera las columnas `date` y `hour` a partir de `datetime`.
- Llama a `fetch_clima_barcelona()` desde `backend/scripts/silver/4.fetch_clima_bcn.py`.
- Realiza un `merge` por `date` y `hour` entre el histórico y el clima, y reindexa a una frecuencia fija de 5 minutos (marcando las filas imputadas en `is_imputed`).

---

## ¿Por qué necesitamos estos datos?

| Necesidad | Dataset / fuente que lo resuelve |
|---|---|
| Saber **dónde** está cada estación | `data/informacion/` |
| Conocer la **capacidad** total de anclajes | `data/informacion/` |
| Ver el **historial** de disponibilidad | `data/estado/` (mensual) |
| Entrenar un modelo de **predicción** | `data/estado/` + clima |
| Filtrar por **tipo de bici** (mecánica / eléctrica) | `data/estado/` |
| Incorporar el impacto del **clima** | API Open-Meteo → `backend/scripts/silver/4.fetch_clima_bcn.py` |
| Unir histórico y clima por estación | `backend/scripts/gold/bikes.py` |
| Entrenar y versionar modelos por estación | `backend/scripts/train_all_stations.py` + MLflow |

---


