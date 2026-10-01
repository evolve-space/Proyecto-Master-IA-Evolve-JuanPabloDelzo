"""Configuración y helpers de acceso a MySQL.

Las credenciales se leen desde variables de entorno (opcionalmente cargadas
desde un archivo `.env` en la raíz del proyecto) para evitar exponerlas
directamente en el código fuente.

Crea un archivo `.env` en la raíz del proyecto (mismo nivel que
`requirements.txt`) a partir de `.env.example` con tus propias credenciales.
"""

from .config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def get_connection_params(database: str | None = None) -> dict:
    """
    Construye el diccionario de parámetros de conexión para
    `mysql.connector.connect(**params)`.

    Args:
        database: nombre de la base de datos a la que conectar. Si es None,
            no se incluye la clave "database" (útil para crear la BD).

    Returns:
        dict con host, port, user, password y, opcionalmente, database.
    """
    if not DB_PASSWORD:
        raise RuntimeError(
            "La variable de entorno MYSQL_PASSWORD no está definida. "
            "Crea un archivo .env en la raíz del proyecto (ver .env.example) "
            "con tus credenciales de MySQL."
        )

    params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
    }
    if database:
        params["database"] = database
    return params


def get_sqlalchemy_url(database: str = DB_NAME) -> str:
    """Construye la URL de conexión para SQLAlchemy."""
    if not DB_PASSWORD:
        raise RuntimeError(
            "La variable de entorno MYSQL_PASSWORD no está definida. "
            "Crea un archivo .env en la raíz del proyecto (ver .env.example) "
            "con tus credenciales de MySQL."
        )
    return (
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@"
        f"{DB_HOST}:{DB_PORT}/{database}"
    )
