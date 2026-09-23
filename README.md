<div align="center">

# 🚲 Bicing Near Me
### Availability prediction for Bicing stations · Barcelona

![Barcelona](https://img.shields.io/badge/City-Barcelona-blue?style=for-the-badge&logo=mapbox)
![AI Development](https://img.shields.io/badge/Master-AI%20Development-orange?style=for-the-badge)
![Evolve](https://img.shields.io/badge/School-Evolve-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-In%20development-yellow?style=for-the-badge)

</div>

---

## 🎯 What is this project?

A tool that locates the **nearest Bicing station** to a user in Barcelona, showing in real time how many **bikes** they can pick up and how many **docks** are free to return one.

The system goes one step further: it applies **time series prediction models** to anticipate future availability at each station, avoiding unnecessary trips.

---

## 🔍 The problem it solves

> You arrive at a Bicing station and it's empty. Or you try to return the bike and there are no free docks.

This project solves exactly that:

| Need | What the system does |
|---|---|
| 🚲 **Pick up a bike** | Shows nearby stations with bikes available right now |
| 🔒 **Return a bike** | Shows nearby stations with free docks |
| 🔮 **Plan ahead** | Predicts future availability using time series |

---

## ⚙️ How does it work?

```
📍 Your location
      │
      ▼
┌──────────────────────────────────────────┐
│         Nearby stations                  │
│                                          │
│  📍 Passeig de Gràcia,178       · 120m   │
│     🚲 Bikes: 5   🔒 Docks: 3           │
│                                          │
│  📍 Plaça Catalunya             · 340m   │
│     🚲 Bikes: 2   🔒 Docks: 8           │
│                                          │
│  📍 Travesera de les Corts,375  · 480m   │
│     🚲 Bikes: 0   🔒 Docks: 12          │
└──────────────────────────────────────────┘
```

---

## 📦 Project data

The data comes from [Open Data Ajuntament de Barcelona](https://opendata-ajuntament.barcelona.cat) and the **Open-Meteo** API, and is split into three types:

### 🕐 Time history — Station status

Monthly `.csv` files with the real-time status of each station, located in `data/estado/`, from January **2021** to September **2025**.

```
data/
└── estado/
    ├── 2021_01_Gener_BicingNou_ESTACIONS.csv
    ├── 2021_02_Febrer_BicingNou_ESTACIONS.csv
    ├── ...
    └── 2025_09_Setembre_BicingNou_ESTACIONS.csv
```

> 📅 **63 monthly files** · over **5 years** of history

Each record contains: `station_id`, `num_bikes_available`, `num_bikes_available_types.mechanical`, `num_bikes_available_types.ebike`, `num_docks_available`, `is_installed`, `is_renting`, `is_returning`, `status`, and `last_reported`.

---

### 📍 Static data — Station information

Monthly `.csv` files in `data/informacion/` with the fixed (or slow-changing) characteristics of each station: GPS location, total capacity, address, and station type.

```
data/
└── informacion/
    ├── 2021_01_Gener_BicingNou_INFORMACIO.csv
    ├── 2021_02_Febrer_BicingNou_INFORMACIO.csv
    ├── ...
    └── 2025_09_Setembre_BicingNou_INFORMACIO.csv
```

| Field | Description |
|---|---|
| `station_id` | Join key with the history |
| `lat` / `lon` | Coordinates for distance calculation |
| `capacity` | Total number of docks |
| `address` | Name and address |
| `physical_configuration` | Station type |
| `is_charging_station` | Whether it has e-bike charging |

---

### 🌤️ Weather data — Open-Meteo

Hourly Barcelona data obtained from the **Open-Meteo** API (`backend/scripts/silver/4.fetch_clima_bcn.py`).

- **Coordinates:** `41.3851`, `2.1734` (Barcelona)
- **Period:** `2021-01-01` to `2025-09-30`
- **Variables:** `temperature_2m`, `relative_humidity_2m`, `rain`, `cloud_cover`, `wind_speed_10m`
- **Time zone:** `Europe/Madrid`

| Field | Description |
|---|---|
| `date` | Record date (`YYYY-MM-DD`) |
| `hour` | Record hour (`HH`) |
| `temperature_c` | Temperature at 2 m (°C) |
| `relative_humidity_2m` | Relative humidity at 2 m (%) |
| `rain` | Rainfall (mm) |
| `cloud_cover` | Cloud cover (%) |
| `wind_speed_10m` | Wind speed at 10 m (km/h) |
| `is_holiday` | `True` if the date is a holiday in Catalonia |

### 🔗 Relationship between datasets

```
Station information  +  Station status  +  Weather
   (where & what it's like)  (current state)   (weather conditions)
             │                        │                  │
             └────── station_id ──────┘                  │
                                    └────── date + hour ─┘
```

> The `station_id` key joins stations with their history; `date` and `hour` allow cross-referencing station status with weather information.

---

## 📁 Repository structure

```
📂 Proyecto-Bicing/
│
├── 📄 README.md                         ← You are here
├── 📄 .env.example                      ← MySQL credentials template
├── 📄 requirements.txt                  ← Backend dependencies
│
├── 📂 data/                             ← Raw data (ignored in Git)
│   ├── 📂 estado/                       ← Monthly station history
│   └── 📂 informacion/                  ← Station characteristics
│
├── 📂 docs/                             ← Master's deliverables
│   └── 📂 entregas/
│       ├── 📄 01_idea_producto.md       ← Product description
│       ├── 📄 02_datos_necesarios.md    ← Data description
│       ├── 📄 03_modelo_datos.md        ← Data model, Gold layer, API & MLflow
│       ├── 📄 04_analisis_modelado.md   ← Modeling strategy
│       └── 📄 05_diseño_frontal.md      ← Frontend design
│
├── 📂 frontend/                         ← User interface in React + Vite
│   ├── 📄 package.json
│   ├── 📄 pnpm-lock.yaml
│   ├── 📄 vite.config.js
│   ├── 📄 index.html
│   ├── 📂 public/
│   └── 📂 src/
│       ├── 📄 App.jsx
│       ├── 📄 main.jsx
│       └── 📂 assets/
│
├── 📂 backend/                          ← Backend services
│   ├── 📂 api/                          ← REST APIs
│   │   ├── informacion_api.py         ← Stations + predictions (port 5002)
│   │   └── bicis_pred_api.py          ← Standalone predictions API (port 5001)
│   │
│   ├── � scripts/                    ← Training and feature scripts
│   │   ├── lstm_model.py              ← LSTMbicis class: trains and predicts
│   │   ├── train_all_stations.py      ← Trains one model per station and registers it in MLflow
│   │   ├── gold/
│   │   │   └── bikes.py               ← Feature engineering per station
│   │   └── silver/                    ← Bronze → Silver load (MySQL)
│   │       ├── 1.create_db.py
│   │       ├── 2.insert_informacion.py
│   │       ├── 3.insert_estado.py
│   │       ├── 4.fetch_clima_bcn.py
│   │       └── db_config.py           ← MySQL credentials via .env
│   │
│   └── 📂 back_testing/
│
└── 📄 mlflow.db                         ← MLflow tracking database (local, ignored in Git)
```

## ▶️ How to run

1. **Backend** (from the project root):
   ```bash
   python backend/api/informacion_api.py
   ```
   Exposes:
   - `GET http://127.0.0.1:5000/api/informacion`
   - `POST http://127.0.0.1:5000/api/predict`

2. **Frontend**:
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

> **Note**: `backend/api/informacion_api.py` already includes both endpoints; `backend/api/bicis_pred_api.py` is a standalone alternative.

---

## ✅ Why is it useful?

- ⏱️ **Saves time** — no walking to an empty station
- 😌 **Avoids frustration** — you know if there are docks before you arrive
- 🔮 **It's predictive** — anticipates availability using time series
- 📊 **Based on real data** — 5+ years of Bicing Barcelona history

---

