"""ACEest Fitness & Gym - Flask backend, version 2.2.4.

Adds goals, workouts, exercises, body metrics and BMI.
"""
import os
import sqlite3
from datetime import datetime

from flask import Flask, current_app, g, jsonify, request

VERSION = "2.2.4"

PROGRAMS = {
    "Fat Loss (FL) – 3 day": {
        "code": "FL3", "calorie_factor": 22, "desc": "3-day full-body fat loss"},
    "Fat Loss (FL) – 5 day": {
        "code": "FL5", "calorie_factor": 24, "desc": "5-day split, higher volume fat loss"},
    "Muscle Gain (MG) – PPL": {
        "code": "MG", "calorie_factor": 35, "desc": "Push/Pull/Legs hypertrophy"},
    "Beginner (BG)": {
        "code": "BG", "calorie_factor": 26, "desc": "3-day simple beginner full-body"},
}

CLIENT_COLUMNS = [
    "name", "age", "height", "weight", "program", "calories", "target_weight",
    "target_adherence",
]
INT_FIELDS = ('age', 'target_adherence')
FLOAT_FIELDS = ('height', 'weight', 'target_weight')
DATE_FIELDS = ()
TEXT_FIELDS = ()
REQUIRE_PROGRAM = True
MISSING_MESSAGE = "Name and Program required"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    age INTEGER,
    height REAL,
    weight REAL,
    program TEXT,
    calories INTEGER,
    target_weight REAL,
    target_adherence INTEGER
);
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    week TEXT,
    adherence INTEGER
);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    date TEXT,
    workout_type TEXT,
    duration_min INTEGER,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER,
    name TEXT,
    sets INTEGER,
    reps INTEGER,
    weight REAL
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    date TEXT,
    weight REAL,
    waist REAL,
    bodyfat REAL
);
"""


def to_number(value, label, cast=float, positive=False, maximum=None):
    """Convert user input to a number, raising ValueError with a clear message."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = cast(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if (number <= 0 if positive else number < 0) or (maximum is not None and number > maximum):
        raise ValueError(f"{label} is out of range")
    return number


def parse_date(value):
    """Validate a YYYY-MM-DD date and return it in ISO format."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError("Dates must use the format YYYY-MM-DD") from None


def week_label(now=None):
    return (now or datetime.now()).strftime("Week %U - %Y")


def client_exists(db, name):
    return db.execute("SELECT 1 FROM clients WHERE name=?", (name,)).fetchone() is not None


def calculate_calories(weight, program):
    """Daily calorie target = weight (kg) x the program's calorie factor."""
    if program not in PROGRAMS:
        raise ValueError("Unknown program")
    if weight is None or weight <= 0:
        raise ValueError("Weight must be positive")
    return int(weight * PROGRAMS[program]["calorie_factor"])


def calculate_bmi(height_cm, weight_kg):
    """Return (bmi, category, risk note) using the thresholds of the desktop app."""
    if not height_cm or not weight_kg or height_cm <= 0 or weight_kg <= 0:
        raise ValueError("Enter valid height and weight first")
    bmi = round(weight_kg / (height_cm / 100.0) ** 2, 1)
    if bmi < 18.5:
        return bmi, "Underweight", "Potential nutrient deficiency, low energy."
    if bmi < 25:
        return bmi, "Normal", "Low risk if active and strong."
    if bmi < 30:
        return bmi, "Overweight", "Moderate risk; focus on adherence and progressive activity."
    return bmi, "Obese", "Higher risk; prioritize fat loss, consistency, and supervision."


def parse_client(data):
    """Validate a client payload and return only the known, cleaned fields."""
    name = str(data.get("name") or "").strip()
    program = data.get("program")
    has_program = program not in (None, "")
    if not name or (REQUIRE_PROGRAM and not has_program):
        raise ValueError(MISSING_MESSAGE)
    clean = {"name": name}
    if has_program:
        if program not in PROGRAMS:
            raise ValueError("Unknown program")
        clean["program"] = str(program).strip()
    for field in INT_FIELDS + FLOAT_FIELDS:
        raw = data.get(field)
        if raw in (None, ""):
            continue
        cast = int if field in INT_FIELDS else float
        limit = 100 if field == "target_adherence" else None
        clean[field] = to_number(raw, field, cast, positive=True, maximum=limit)
    for field in DATE_FIELDS:
        if data.get(field) not in (None, ""):
            clean[field] = parse_date(data[field])
    for field in TEXT_FIELDS:
        if str(data.get(field) or "").strip():
            clean[field] = str(data[field]).strip()
    return clean


def init_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or os.getenv("DB_PATH", "aceest_fitness.db")
    init_db(app.config["DB_PATH"])

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(current_app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

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
        return jsonify([{"name": n, **info} for n, info in PROGRAMS.items()])

    @app.post("/clients")
    def save_client():
        try:
            clean = parse_client(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        row = db.execute("SELECT * FROM clients WHERE name=?", (clean["name"],)).fetchone()
        merged = {**(dict(row) if row else {}), **clean}
        if merged.get("weight") and merged.get("program") in PROGRAMS:
            merged["calories"] = calculate_calories(merged["weight"], merged["program"])
        cols = [c for c in CLIENT_COLUMNS if c in merged]
        if row:
            sets = ", ".join(f"{c}=?" for c in cols if c != "name")
            db.execute(f"UPDATE clients SET {sets} WHERE name=?",
                       [merged[c] for c in cols if c != "name"] + [clean["name"]])
        else:
            marks = ", ".join("?" for _ in cols)
            db.execute(f"INSERT INTO clients ({', '.join(cols)}) VALUES ({marks})",
                       [merged[c] for c in cols])
        db.commit()
        return jsonify(message="Client data saved", calories=merged.get("calories")), \
            (200 if row else 201)

    @app.get("/clients/<name>")
    def get_client(name):
        row = get_db().execute("SELECT * FROM clients WHERE name=?", (name,)).fetchone()
        if row is None:
            return jsonify(error="Client not found"), 404
        data = dict(row)
        data.pop("id")
        return jsonify(data)

    @app.get("/clients")
    def list_clients():
        rows = get_db().execute("SELECT name FROM clients ORDER BY name").fetchall()
        return jsonify([r["name"] for r in rows])

    @app.post("/clients/<name>/progress")
    def save_progress(name):
        adherence = (request.get_json(silent=True) or {}).get("adherence")
        if isinstance(adherence, bool) or not isinstance(adherence, int) \
                or not 0 <= adherence <= 100:
            return jsonify(error="adherence must be an integer 0-100"), 400
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        week = week_label()
        db.execute("INSERT INTO progress (client_name, week, adherence) VALUES (?, ?, ?)",
                   (name, week, adherence))
        db.commit()
        return jsonify(message="Weekly progress logged", week=week), 201

    @app.get("/clients/<name>/progress")
    def list_progress(name):
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        rows = db.execute("SELECT week, adherence FROM progress WHERE client_name=? ORDER BY id",
                          (name,)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/clients/<name>/metrics")
    def log_metrics(name):
        data = request.get_json(silent=True) or {}
        try:
            if not data.get("date"):
                raise ValueError("Date is required")
            m_date = parse_date(data["date"])
            weight = to_number(data.get("weight", 0), "weight")
            waist = to_number(data.get("waist", 0), "waist")
            bodyfat = to_number(data.get("bodyfat", 0), "bodyfat", maximum=100)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        db.execute("INSERT INTO metrics (client_name, date, weight, waist, bodyfat) "
                   "VALUES (?, ?, ?, ?, ?)", (name, m_date, weight, waist, bodyfat))
        db.commit()
        return jsonify(message="Metrics logged"), 201

    @app.get("/clients/<name>/metrics")
    def list_metrics(name):
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        rows = db.execute("SELECT date, weight, waist, bodyfat FROM metrics "
                          "WHERE client_name=? ORDER BY date, id", (name,)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/clients/<name>/bmi")
    def client_bmi(name):
        row = get_db().execute("SELECT height, weight FROM clients WHERE name=?",
                               (name,)).fetchone()
        if row is None:
            return jsonify(error="Client not found"), 404
        try:
            bmi, category, risk = calculate_bmi(row["height"], row["weight"])
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(bmi=bmi, category=category, risk=risk)

    @app.post("/clients/<name>/workouts")
    def log_workout(name):
        data = request.get_json(silent=True) or {}
        w_type = str(data.get("workout_type") or "").strip()
        exercise = data.get("exercise")
        try:
            if not data.get("date") or not w_type:
                raise ValueError("Date and workout type are required")
            w_date = parse_date(data["date"])
            duration = to_number(data.get("duration_min", 60), "duration_min", int)
            if exercise:
                if not isinstance(exercise, dict) or not str(exercise.get("name") or "").strip():
                    raise ValueError("exercise needs a name")
                ex_values = (str(exercise["name"]).strip(),
                             to_number(exercise.get("sets", 3), "sets", int, positive=True),
                             to_number(exercise.get("reps", 10), "reps", int, positive=True),
                             to_number(exercise.get("weight", 0), "weight"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        notes = str(data.get("notes") or "").strip()
        cur = db.execute("INSERT INTO workouts (client_name, date, workout_type, duration_min, "
                         "notes) VALUES (?, ?, ?, ?, ?)", (name, w_date, w_type, duration, notes))
        if exercise:
            db.execute("INSERT INTO exercises (workout_id, name, sets, reps, weight) "
                       "VALUES (?, ?, ?, ?, ?)", (cur.lastrowid, *ex_values))
        db.commit()
        return jsonify(message="Workout logged", id=cur.lastrowid), 201

    @app.get("/clients/<name>/workouts")
    def list_workouts(name):
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        rows = db.execute("SELECT id, date, workout_type, duration_min, notes FROM workouts "
                          "WHERE client_name=? ORDER BY date DESC, id DESC", (name,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            exercises = db.execute("SELECT name, sets, reps, weight FROM exercises "
                                   "WHERE workout_id=? ORDER BY id", (item.pop("id"),)).fetchall()
            item["exercises"] = [dict(e) for e in exercises]
            result.append(item)
        return jsonify(result)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
