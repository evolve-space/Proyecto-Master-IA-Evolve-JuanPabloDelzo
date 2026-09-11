import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

import holidays
import pandas as pd

LAT, LON = 41.3851, 2.1734
START = "2021-01-01"
END = "2025-09-30"

_ES_HOLIDAYS = holidays.ES(subdiv="CT", years=range(2021, 2026))

def fetch_chunk(start, end):
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start,
        "end_date": end,
        "hourly": (
            "temperature_2m,relative_humidity_2m,rain,cloud_cover,"
            "wind_speed_10m"
        ),
        "timezone": "Europe/Madrid",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urlencode(params)
    with urlopen(url, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_clima_barcelona(start=START, end=END):
    records = []
    current = datetime.strptime(start, "%Y-%m-%d")
    final = datetime.strptime(end, "%Y-%m-%d")

    while current <= final:
        chunk_end = min(datetime(current.year, 12, 31), final)
        start_str = current.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")
        #print(f"Descargando {start_str} a {end_str}...")

        data = fetch_chunk(start_str, end_str)
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        def _get(key):
            return hourly.get(key, [None] * len(times))

        temps = _get("temperature_2m")
        humidity = _get("relative_humidity_2m")
        rain = _get("rain")
        cloud_cover = _get("cloud_cover")
        wind_speed = _get("wind_speed_10m")

        for (
            t,
            temp,
            hum,
            rain_val,
            cloud,
            wind,
        ) in zip(
            times,
            temps,
            humidity,
            rain,
            cloud_cover,
            wind_speed,
        ):
            dt = datetime.fromisoformat(t)
            date_str = dt.strftime("%Y-%m-%d")
            records.append(
                {
                    "date": date_str,
                    "hour": dt.hour,
                    "temperature_c": temp,
                    "relative_humidity_2m": hum,
                    "rain": rain_val,
                    "cloud_cover": cloud,
                    "wind_speed_10m": wind,
                    "is_holiday": date_str in _ES_HOLIDAYS,
                }
            )

        current = chunk_end + timedelta(days=1)

    return pd.DataFrame(
        records,
        columns=[
            "date",
            "is_holiday",
            "hour",
            "temperature_c",
            "relative_humidity_2m",
            "rain",
            "cloud_cover",
            "wind_speed_10m",
        ],
    )


if __name__ == "__main__":
    df = fetch_clima_barcelona()
    print("\nViendo valores nulos:")
    print(df.isnull().sum())
    print(df.head(10))
    print(f"Total filas: {len(df)}")
