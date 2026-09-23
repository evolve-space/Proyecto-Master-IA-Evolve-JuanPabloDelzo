# 🚲 Bicing Cerca de Mí 

## ¿Qué es?

Una herramienta sencilla que te ayuda a encontrar **la estación de Bicing más cercana** a tu ubicación en Barcelona, tanto si quieres **coger una bicicleta** como si quieres **devolver una**, y que además predice la disponibilidad futura usando datos históricos y meteorológicos.

---

## ¿Para qué sirve?

Cuando usas el servicio público de bicicletas `Bicing` en Barcelona, tienes dos necesidades principales:

1. **Coger una bici** → necesitas saber qué estación cercana tiene bicis disponibles.
2. **Devolver una bici** → necesitas saber qué estación cercana tiene anclajes libres.
3. **Planificar** → saber con antelación cuándo y dónde habrá bicis o anclajes libres según el clima y la hora.

Este producto resuelve estas situaciones de forma rápida y clara, combinando información en tiempo real, histórico y predicción.

---

## ¿Cómo funciona?

1. El usuario indica su ubicación (o se detecta automáticamente).
2. El sistema localiza las estaciones de Bicing más cercanas.
3. Se muestra para cada estación:
   - 🚲 **Bicicletas disponibles** para coger.
   - 🔒 **Anclajes libres** para devolver.
4. El modelo de series temporales estima la disponibilidad futura a partir del histórico, las condiciones meteorológicas y el indicador de día festivo.

---

## Ejemplo visual del flujo

```
📍 Tu ubicación
      │
      ▼
┌─────────────────────────────────────┐
│  Estaciones cercanas                │
│                                     │
│  📍 Estación Passeig de Gràcia     │
│     🚲 Bicis disponibles: 5        │
│     🔒 Anclajes libres: 3          │
│                                     │
│  📍 Estación Plaça Catalunya       │
│     🚲 Bicis disponibles: 2        │
│     🔒 Anclajes libres: 8          │
│                                     │
│  📍 Estación Eixample              │
│     🚲 Bicis disponibles: 0        │
│     🔒 Anclajes libres: 12         │
└─────────────────────────────────────┘
```

---

## ¿Qué información muestra?

| Información | Descripción |
|---|---|
| 📍 Nombre de la estación | Identificación de la parada Bicing |
| 📏 Distancia | Metros desde tu posición actual |
| 🚲 Bicis disponibles | Cuántas bicicletas puedes coger ahora mismo |
| 🔒 Anclajes libres | Cuántos sitios tienes para devolver la bici |
| 🌤️ Condición meteorológica | Estado del tiempo que puede influir en la demanda |
| 🎉 Día festivo | Indica si la fecha es festivo en Cataluña, afectando la demanda de Bicing |
| 🔮 Predicción | Disponibilidad estimada en los próximos minutos/horas |

---

## ¿Por qué es útil?

- **Ahorra tiempo**: no caminas hasta una estación vacía.
- **Evita frustraciones**: sabes de antemano si hay anclajes libres para devolver.
- **Es simple**: la información es directa, sin tecnicismos.
- **Es predictivo**: anticipa la disponibilidad futura a 5 y 10 minutos usando modelos LSTM entrenados por estación y registrados en MLflow.
- **Modelos versionados**: cada estación tiene su propio modelo (`est_{station_id}`) en el Model Registry de MLflow, lo que permite cargarlo y predecir sin reentrenar.

---

## Tecnología base

Los datos provienen del [Open Data del Ajuntament de Barcelona](https://opendata-ajuntament.barcelona.cat) (información y estado de estaciones), de la API de [Open-Meteo](https://open-meteo.com/) (datos meteorológicos históricos de Barcelona) y del calendario de festivos de Cataluña, combinados para alimentar modelos de predicción de series temporales.

Cada estación dispone de un modelo LSTM propio entrenado con su histórico y registrado en MLflow (`est_{station_id}`). La interfaz de usuario está desarrollada en **React** con **Vite** y gestionada con `pnpm`, consumiendo las predicciones del backend a través de una API REST Flask en el puerto `5002`.

---


