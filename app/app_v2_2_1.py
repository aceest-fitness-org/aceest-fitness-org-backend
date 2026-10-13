"""ACEest Fitness & Gym - Flask backend, version 2.2.1.

Adds progress history for the adherence chart.
"""
import os
import sqlite3
from datetime import datetime

from flask import Flask, current_app, g, jsonify, request

VERSION = "2.2.1"

PROGRAMS = {
    "Fat Loss (FL)": {"code": "FL", "calorie_factor": 22},
    "Muscle Gain (MG)": {"code": "MG", "calorie_factor": 35},
    "Beginner (BG)": {"code": "BG", "calorie_factor": 26},
}

CLIENT_COLUMNS = [
    "name", "age", "weight", "program", "calories",
]
INT_FIELDS = ('age',)
FLOAT_FIELDS = ('weight',)
DATE_FIELDS = ()
TEXT_FIELDS = ()
REQUIRE_PROGRAM = True
MISSING_MESSAGE = "Name and Program required"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    age INTEGER,
    weight REAL,
    program TEXT,
    calories INTEGER
);
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    week TEXT,
    adherence INTEGER
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

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
