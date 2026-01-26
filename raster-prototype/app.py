import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS

from raster_gcode import generate_raster_gcode

APP_ROOT = Path(__file__).parent
FRONTEND_PATH = APP_ROOT / "frontend"

PORT = int(os.environ.get("PORT", "8010"))
DEBUG = str(os.environ.get("DEBUG", "")).strip().lower() in ("1", "true", "yes")

app = Flask(__name__)
CORS(app)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/generate-raster", methods=["POST"])
def api_generate_raster():
    data = request.get_json(force=True, silent=False) or {}
    try:
        gcode = generate_raster_gcode(
            image_base64=data.get("image_base64", ""),
            speed=int(data.get("speed", 1796)),
            power=float(data.get("power", 100.0)),
            passes=int(data.get("passes", 1)),
            origin=str(data.get("origin", "bottom-left")),
            mm_per_pixel=float(data.get("mm_per_pixel", 0.1)),
            width_mm=float(data["width_mm"]) if "width_mm" in data and data["width_mm"] not in (None, "", 0) else None,
            height_mm=float(data["height_mm"]) if "height_mm" in data and data["height_mm"] not in (None, "", 0) else None,
            invert_image=bool(data.get("invert_image", False)),
            shading=str(data.get("shading", "grayscale")),
            gamma=float(data.get("gamma", 1.0)),
            levels=int(data.get("levels", 0)),
            thumbnail_mode=str(data.get("thumbnail_mode", "match-input")),
            thumbnail_contrast=float(data.get("thumbnail_contrast", 1.0)),
            safe_mode=bool(data.get("safe_mode", False)),
        )
        return jsonify({"gcode": gcode})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/raster")
def raster_page():
    return send_from_directory(str(FRONTEND_PATH), "raster.html")


@app.route("/")
def root():
    return jsonify({"service": "okudesk-raster-prototype", "raster": "/raster"})


@app.route("/<path:filename>")
def static_files(filename: str):
    # prevent API paths from being treated as static
    if filename.startswith("api/"):
        abort(404)
    return send_from_directory(str(FRONTEND_PATH), filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)

