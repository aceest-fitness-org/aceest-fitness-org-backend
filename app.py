"""ACEest Fitness & Gym - Flask backend, version 1.1.

Program catalogue with workout and diet plans.
"""
import os

from flask import Flask, jsonify

VERSION = "1.1"

PROGRAMS = {
    "FL": {
        "name": "Fat Loss (FL)",
        "workout": ("Mon: Back Squat 5x5 + Core\nTue: EMOM 20min Assault Bike\n"
                    "Wed: Bench Press + 21-15-9\nThu: Deadlift + Box Jumps\n"
                    "Fri: Zone 2 Cardio 30min"),
        "diet": ("Breakfast: Egg Whites + Oats\nLunch: Grilled Chicken + Brown Rice\n"
                 "Dinner: Fish Curry + Millet Roti\nTarget: ~2000 kcal"),
        "color": "#e74c3c",
        "calorie_factor": 22,
    },
    "MG": {
        "name": "Muscle Gain (MG)",
        "workout": ("Mon: Squat 5x5\nTue: Bench 5x5\nWed: Deadlift 4x6\n"
                    "Thu: Front Squat 4x8\nFri: Incline Press 4x10\nSat: Barbell Rows 4x10"),
        "diet": ("Breakfast: Eggs + Peanut Butter Oats\nLunch: Chicken Biryani\n"
                 "Dinner: Mutton Curry + Rice\nTarget: ~3200 kcal"),
        "color": "#2ecc71",
        "calorie_factor": 35,
    },
    "BG": {
        "name": "Beginner (BG)",
        "workout": ("Full Body Circuit:\n- Air Squats\n- Ring Rows\n- Push-ups\n"
                    "Focus: Technique & Consistency"),
        "diet": ("Balanced Tamil Meals\nIdli / Dosa / Rice + Dal\n"
                 "Protein Target: 120g/day"),
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
