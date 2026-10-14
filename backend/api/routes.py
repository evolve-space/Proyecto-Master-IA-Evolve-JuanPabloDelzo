import traceback

from flask import Blueprint, jsonify, request

from .services import ResourceNotFoundError, get_stations, predict_availability

api = Blueprint("api", __name__)


@api.get("/health")
def health():
    return jsonify({"status": "ok"})


@api.get("/informacion")
def station_information():
    try:
        return jsonify(get_stations())
    except Exception as error:
        traceback.print_exc()
        return jsonify({"error": str(error)}), 500


@api.post("/predict")
def predict():
    data = request.get_json(silent=True) or {}
    station_id = data.get("station_id")
    if station_id is None:
        return jsonify({"error": "station_id es obligatorio"}), 400

    try:
        station_id = int(station_id)
    except (TypeError, ValueError):
        return jsonify({"error": "station_id debe ser un número entero"}), 400

    try:
        return jsonify(predict_availability(station_id))
    except ResourceNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        traceback.print_exc()
        return jsonify({"error": str(error)}), 500
