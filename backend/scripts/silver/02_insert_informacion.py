import csv
import sys
from pathlib import Path

import polars as pl
import mysql.connector
from mysql.connector import Error

from db_config import get_connection_params

INFORMACION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "informacion"
files = sorted(INFORMACION_DIR.glob("*.csv"))

ATRIBUTOS = [
    "station_id",
    "physical_configuration",
    "lat",
    "lon",
    "address",
    "post_code",
    "capacity",
    "last_updated",
]

COLUMNAS_FINALES = [
    "station_id",
    "physical_configuration",
    "latitud",
    "longitud",
    "address",
    "post_code",
    "capacity",
    "last_update",
]

INSERT_INFORMACION = """
    INSERT INTO informacion (
        station_id,
        physical_configuration,
        latitud,
        longitud,
        address,
        post_code,
        capacity,
        last_update
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        physical_configuration = VALUES(physical_configuration),
        latitud = VALUES(latitud),
        longitud = VALUES(longitud),
        address = VALUES(address),
        post_code = VALUES(post_code),
        capacity = VALUES(capacity),
        last_update = VALUES(last_update)
"""


def _header_columns(file):
    with open(file, "r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return [col.strip().strip('"') for col in line.split(",") if col.strip()]


def _read_informacion_csv(file):
    present_cols = [col for col in _header_columns(file) if col in ATRIBUTOS]
    for encoding in ("utf8", "windows-1252", "utf8-lossy"):
        try:
            return pl.read_csv(
                file,
                columns=present_cols,
                schema_overrides={"post_code": pl.Utf8},
                encoding=encoding,
                try_parse_dates=False,
                null_values=["NA", "N/A", "NULL", "null", "None", "NaN", "nan"],
            )
        except (UnicodeDecodeError, pl.exceptions.ComputeError):
            continue
    raise RuntimeError(f"No se pudo leer {file} con utf8, windows-1252 ni utf8-lossy")


def _formato_cp(cp):
    if cp is None:
        return None
    cp = cp.strip()
    if not cp.isdigit() or len(cp) > 5:
        return None
    return cp.zfill(5)


def _normalizar_df(df):
    df = df.filter(pl.col("station_id").is_not_null())
    df = df.with_columns(pl.col("station_id").cast(pl.Int64, strict=False))

    df = df.rename({"lat": "latitud", "lon": "longitud"}, strict=False)

    if "last_updated" in df.columns:
        df = (
            df.with_columns(
                pl.from_epoch(
                    pl.col("last_updated").cast(pl.Int64, strict=False),
                    time_unit="s",
                ).alias("last_update")
            )
            .drop("last_updated")
        )

    expected = {
        "station_id": pl.Int64,
        "physical_configuration": pl.Utf8,
        "latitud": pl.Float64,
        "longitud": pl.Float64,
        "address": pl.Utf8,
        "post_code": pl.Utf8,
        "capacity": pl.Int64,
        "last_update": pl.Datetime("us"),
    }

    for col, dtype in expected.items():
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dtype).alias(col))
        else:
            df = df.with_columns(pl.col(col).cast(dtype, strict=False))

    df = df.with_columns(
        pl.col("post_code").map_elements(_formato_cp, return_dtype=pl.Utf8)
    )

    df = df.unique(subset=["station_id"], keep="last", maintain_order=True)
    return df.select(list(expected.keys()))


def load_informacion():
    partes = []
    for file in files:
        df = _read_informacion_csv(file)
        df = _normalizar_df(df)
        partes.append(df)
        print(f"Procesado {file.name}: {df.height} estaciones")

    dimension = pl.concat(partes, how="vertical")
    dimension = dimension.unique(subset=["station_id"], keep="last", maintain_order=True)
    return dimension


def insert_informacion(dataframe):
    connection = None
    try:
        connection = mysql.connector.connect(**get_connection_params("Bicing"))
        cursor = connection.cursor()
        batch_size = 10_000
        for start in range(0, dataframe.height, batch_size):
            batch = dataframe.slice(start, batch_size)
            rows = [tuple(row) for row in batch.iter_rows(named=False)]
            cursor.executemany(INSERT_INFORMACION, rows)
            connection.commit()
        cursor.close()
        print(f"{dataframe.height} estaciones insertadas en informacion.")
    except Error as error:
        print(f"No se pudieron insertar las estaciones: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    insert_informacion(load_informacion())
