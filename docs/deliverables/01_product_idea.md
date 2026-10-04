# 🚲 Bicing Near Me

## What is it?

A simple tool that helps you find the **nearest Bicing station** to your location in Barcelona, whether you want to **pick up a bicycle** or **return one**, and that also predicts future availability using historical and weather data.

---

## What is it for?

When you use the public `Bicing` bike service in Barcelona, you have three main needs:

1. **Pick up a bike** → you need to know which nearby station has bikes available.
2. **Return a bike** → you need to know which nearby station has free docks.
3. **Plan ahead** → know in advance when and where bikes or free docks will be available depending on the weather and time of day.

This product resolves these situations quickly and clearly by combining real-time, historical, and predictive information.

---

## How does it work?

1. The user indicates their location (or it is detected automatically).
2. The system locates the nearest Bicing stations.
3. For each station it shows:
   - 🚲 **Available bikes** to pick up.
   - 🔒 **Free docks** to return.
4. The time series model estimates future availability based on historical data, weather conditions, and the holiday indicator.

---

## Visual example of the flow

```
📍 Your location
      │
      ▼
┌─────────────────────────────────────┐
│  Nearby stations                    │
│                                     │
│  📍 Passeig de Gràcia station      │
│     🚲 Available bikes: 5          │
│     🔒 Free docks: 3               │
│                                     │
│  📍 Plaça Catalunya station        │
│     🚲 Available bikes: 2          │
│     🔒 Free docks: 8               │
│                                     │
│  📍 Eixample station               │
│     🚲 Available bikes: 0          │
│     🔒 Free docks: 12              │
└─────────────────────────────────────┘
```

---

## What information does it show?

| Information | Description |
|---|---|
| 📍 Station name | Identification of the Bicing stop |
| 📏 Distance | Meters from your current position |
| 🚲 Available bikes | How many bicycles you can pick up right now |
| 🔒 Free docks | How many slots you have to return the bike |
| 🌤️ Weather condition | Weather status that can influence demand |
| 🎉 Holiday | Indicates whether the date is a holiday in Catalonia, affecting Bicing demand |
| 🔮 Prediction | Estimated availability in the next minutes/hours |

---

## Why is it useful?

- **Saves time**: you do not walk to an empty station.
- **Avoids frustration**: you know in advance if there are free docks to return the bike.
- **It is simple**: the information is direct, with no technical jargon.
- **It is predictive**: it anticipates future availability at 5 and 10 minutes using LSTM models trained per station and registered in MLflow.
- **Versioned models**: each station has its own model (`est_{station_id}`) in the MLflow Model Registry, which allows loading and predicting without retraining.

---

## Base technology

The data comes from the [Barcelona City Council Open Data portal](https://opendata-ajuntament.barcelona.cat) (station information and status), the [Open-Meteo](https://open-meteo.com/) API (historical weather data for Barcelona), and the Catalonia holiday calendar, combined to feed time series prediction models.

Each station has its own LSTM model trained with its own history and registered in MLflow (`est_{station_id}`). The user interface is developed in **React** with **Vite** and managed with `pnpm`, consuming predictions from the backend through a REST API Flask on port `5002`.

---
