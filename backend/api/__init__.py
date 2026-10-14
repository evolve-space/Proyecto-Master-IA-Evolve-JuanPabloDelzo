import os

from flask import Flask
from flask_cors import CORS

from backend.core.mlflow_client import setup_mlflow


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        API_HOST=os.getenv("API_HOST", "0.0.0.0"),
        API_PORT=int(os.getenv("API_PORT", "5002")),
    )
    if config:
        app.config.update(config)

    CORS(app)
    setup_mlflow()

    from .routes import api

    app.register_blueprint(api, url_prefix="/api")
    return app
