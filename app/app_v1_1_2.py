"""ACEest Fitness & Gym - Flask backend, version 1.1.2.

Program catalogue (compact plans) for the client table UI.
"""
import os

from flask import Flask, jsonify

VERSION = "1.1.2"

PROGRAMS = {
    "FL": {
        "name": "Fat Loss (FL)",
        "workout": "Back Squat, Cardio, Bench, Deadlift, Recovery",
        "diet": "Egg Whites, Chicken, Fish Curry",
        "color": "#e74c3c",
        "calorie_factor": 22,
    },
    "MG": {
        "name": "Muscle Gain (MG)",
        "workout": "Squat, Bench, Deadlift, Press, Rows",
        "diet": "Eggs, Biryani, Mutton Curry",
        "color": "#2ecc71",
        "calorie_factor": 35,
    },
    "BG": {
        "name": "Beginner (BG)",
        "workout": "Air Squats, Ring Rows, Push-ups",
        "diet": "Balanced Tamil Meals",
        "color": "#3498db",
        "calorie_factor": 26,
    },
}


def find_program(key):
    """Look up a program by code ('FL') or full name ('Fat Loss (FL)')."""
    key = str(key).strip().lower()
    for code, data in PROGRAMS.items():
        if key in (code.lower(), data["name"].lower()):
            return code, data
    return None, None


def create_app():
    app = Flask(__name__)

    @app.after_request
    def add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = os.getenv("CORS_ORIGIN", "*")
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @app.get("/health")
    def health():
        return jsonify(status="ok", version=VERSION)

    @app.get("/programs")
    def list_programs():
        return jsonify([{"code": c, "name": d["name"], "color": d["color"],
                         "calorie_factor": d["calorie_factor"]} for c, d in PROGRAMS.items()])

    @app.get("/programs/<key>")
    def program_detail(key):
        code, data = find_program(key)
        if data is None:
            return jsonify(error="Program not found"), 404
        return jsonify(code=code, **data)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
