"""Feature engineering: carga del histórico de estaciones, unión con clima y
reconstrucción de la serie a frecuencia fija.

Este módulo contiene la lógica que antes vivía en
`backend/scripts/gold/bikes.py`. Lo hemos movido a `backend/core` porque es
usado tanto por el entrenamiento como por la API de predicción.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from .db import get_sqlalchemy_url


def _import_fetch_clima_bcn():
    """Importa la función fetch_clima_barcelona desde el script silver/04_fetch_clima_bcn.py."""
    module_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "silver" / "04_fetch_clima_bcn.py"
    )
    spec = importlib.util.spec_from_file_location("fetch_clima_bcn", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_clima_bcn"] = module
    spec.loader.exec_module(module)
    return module.fetch_clima_barcelona


# Cache en memoria del DataFrame de clima: los datos son históricos con
# rango fijo (2021-01-01 a 2025-09-30), por lo que descargarlos de
# Open-Meteo en cada llamada a `bicis` es innecesario y muy lento.
_CLIMA_CACHE = None


def cargar_estado_station(station_id: int, since: str = "2021-01-01"):
    """
    Carga el estado de una estación desde la base de datos.

    Args:
        station_id: ID de la estación a consultar.
        since: fecha mínima (inclusive) en formato 'YYYY-MM-DD' desde la
            que cargar el histórico. Por defecto carga todo desde 2021;
            para inferencia en tiempo real basta con los últimos días.

    Returns:
        DataFrame con el estado de la estación.
    """
    query = """
          WITH aux_table AS (
          SELECT
              datetime,
              num_bikes_available_mechanical AS nbm,
              num_bikes_available_ebike AS nbe,
              HOUR(datetime) AS hour,
              HOUR(datetime) + MINUTE(datetime)/60 AS h,
              dayofweek(datetime) AS day_week,
              DAYOFYEAR(datetime) AS day_year,
              CASE
                  WHEN DAYOFYEAR(CONCAT(YEAR(datetime), '-12-31')) = 366 THEN 366
                  ELSE 365
              END AS days_in_year
          FROM estado
          WHERE station_id = %s AND datetime >= %s
          ORDER BY datetime ASC)
          SELECT 
              datetime,
              nbm,
              nbe,
              LAG(nbm,1)
                  OVER(ORDER BY datetime) AS lag_nbm,
              LAG(nbe,1)
                  OVER(ORDER BY datetime) AS lag_nbe,
              hour,
              ROUND(SIN(2*PI()*h/24),4) AS hour_sin, 
              ROUND(COS(2*PI()*h/24),4) AS hour_cos, 
              ROUND(SIN(2*PI()*day_week/7),4) AS dow_sin,
              ROUND(COS(2*PI()*day_week/7),4) AS dow_cos,
              ROUND(SIN(2*PI()*day_year/days_in_year),4) AS year_sin,
              ROUND(COS(2*PI()*day_year/days_in_year),4) AS year_cos
          FROM aux_table
          """
    engine = create_engine(get_sqlalchemy_url())
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=(station_id, since))
    return df


def bicis(station_id: int, since: str = "2021-01-01"):
    """
    Carga el estado de una estación y el clima de Barcelona,
    luego une ambos datasets por fecha y hora.

    Args:
        station_id: ID de la estación a consultar.
        since: fecha mínima (inclusive) en formato 'YYYY-MM-DD' desde la
            que cargar el histórico de la estación. El clima se cachea en
            memoria tras la primera descarga.

    Returns:
        DataFrame con el estado de la estación y el clima, indexado por datetime.
    """
    global _CLIMA_CACHE

    # 1. Estado de la estación.
    df_estado = cargar_estado_station(station_id, since=since)
    df_estado = df_estado.assign(
        datetime=pd.to_datetime(df_estado.datetime),
        date=df_estado.datetime.dt.strftime("%Y-%m-%d"),
    )

    # 2. Clima y festivos (cacheado: el rango histórico es fijo).
    if _CLIMA_CACHE is None:
        fetch_clima_barcelona = _import_fetch_clima_bcn()
        _CLIMA_CACHE = fetch_clima_barcelona()
    df_clima = _CLIMA_CACHE

    # 3. Unión de los dos datasets.
    df_merged = pd.merge(
        df_estado,
        df_clima,
        on=["date", "hour"],
        how="left",
    )
    df_merged.set_index("datetime", inplace=True)
    df_merged = df_merged.drop(columns=["date", "hour"])

    # 4. Reindexar a frecuencia fija de 5 minutos y marcar filas imputadas.
    original_index = df_merged.index
    df_merged_filled = df_merged.asfreq("5min", method="ffill")
    df_merged_filled["is_imputed"] = ~df_merged_filled.index.isin(original_index)

    return df_merged_filled


if __name__ == "__main__":
    id_est = 44
    df = bicis(id_est)
    print(f"\nEstación {id_est}:")
    print(df.tail(10))
    print("\nValores nulos:")
    print(df.isnull().sum())
    print(f"Total filas: {len(df)}")
