import sys

import mysql.connector
from mysql.connector import Error

from db_config import get_connection_params

DATABASE_NAME = "Bicing"


def create_database(cursor):
    cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE_NAME}`")
    cursor.execute(
        f"CREATE DATABASE `{DATABASE_NAME}` "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )


def create_tables(connection):
    cursor = connection.cursor()
    cursor.execute(
        """
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
        )
        """
    )
    cursor.execute(
        """
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
        )
        """
    )
    connection.commit()
    cursor.close()


def main():
    connection = None

    try:
        connection = mysql.connector.connect(**get_connection_params())
        cursor = connection.cursor()
        create_database(cursor)
        cursor.close()
        connection.database = DATABASE_NAME
        create_tables(connection)
        print("Base de datos Bicing restaurada.")
    except Error as error:
        print(f"No se pudo crear la base de datos: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()
