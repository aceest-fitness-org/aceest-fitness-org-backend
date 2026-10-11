from flask import Flask, jsonify

PROGRAMS = {
    "FL": {
        "name": "Fat Loss (FL)",
        "workout": (
            "Mon: 5x5 Back Squat + AMRAP\n"
            "Tue: EMOM 20min Assault Bike\n"
            "Wed: Bench Press + 21-15-9\n"
            "Thu: 10RFT Deadlifts/Box Jumps\n"
            "Fri: 30min Active Recovery"
        ),
        "diet": (
            "B: 3 Egg Whites + Oats Idli\n"
            "L: Grilled Chicken + Brown Rice\n"
            "D: Fish Curry + Millet Roti\n"
            "Target: 2,000 kcal"
        ),
        "color": "#e74c3c",
    },
    "MG": {
        "name": "Muscle Gain (MG)",
        "workout": (
            "Mon: Squat 5x5\n"
            "Tue: Bench 5x5\n"
            "Wed: Deadlift 4x6\n"
            "Thu: Front Squat 4x8\n"
            "Fri: Incline Press 4x10\n"
            "Sat: Barbell Rows 4x10"
        ),
        "diet": (
            "B: 4 Eggs + PB Oats\n"
            "L: Chicken Biryani (250g Chicken)\n"
            "D: Mutton Curry + Jeera Rice\n"
            "Target: 3,200 kcal"
        ),
        "color": "#2ecc71",
    },
    "BG": {
        "name": "Beginner (BG)",
        "workout": (
            "Circuit Training: Air Squats, Ring Rows, Push-ups.\n"
            "Focus: Technique Mastery & Form (90% Threshold)"
        ),
        "diet": (
            "Balanced Tamil Meals: Idli-Sambar, Rice-Dal, Chapati.\n"
            "Protein: 120g/day"
        ),
        "color": "#3498db",
    },
}

METRICS = {"capacity_users": 150, "area_sqft": 10000, "break_even_members": 250}


def find_program(key):
    """Look up a program by code ('FL') or full name ('Fat Loss (FL)')."""
    key = key.strip().lower()
    for code, data in PROGRAMS.items():
        if key == code.lower() or key == data["name"].lower():
            return code, data
    return None, None


def create_app():
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/programs")
    def list_programs():
        return jsonify(
            [{"code": c, "name": d["name"], "color": d["color"]} for c, d in PROGRAMS.items()]
        )

    @app.get("/programs/<key>")
    def program_detail(key):
        code, data = find_program(key)
        if data is None:
            return jsonify(error="Program not found"), 404
        return jsonify(code=code, **data)

    @app.get("/metrics")
    def metrics():
        return jsonify(METRICS)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
    