"""ACEest Fitness & Gym - Flask backend, version 3.1.2.

Adds login, membership expiry, AI program generator and PDF report.
"""
import os
import random
import re
import sqlite3
from datetime import date, datetime

from flask import Flask, Response, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

VERSION = "3.1.2"

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
    "target_adherence", "membership_expiry",
]
INT_FIELDS = ('age', 'target_adherence')
FLOAT_FIELDS = ('height', 'weight', 'target_weight')
DATE_FIELDS = ('membership_expiry',)
TEXT_FIELDS = ()
REQUIRE_PROGRAM = True
MISSING_MESSAGE = "Name and Program required"
REPORT_FIELDS = [
    ("Name", "name"), ("Age", "age"), ("Height", "height"), ("Weight", "weight"),
    ("Program", "program"), ("Calories", "calories"), ("Target Weight", "target_weight"),
    ("Target Adherence", "target_adherence"), ("Membership Expiry", "membership_expiry"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    age INTEGER,
    height REAL,
    weight REAL,
    program TEXT,
    calories INTEGER,
    target_weight REAL,
    target_adherence INTEGER,
    membership_expiry TEXT
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


def is_membership_expired(end, today=None):
    """True when the membership end date is before today."""
    if not end:
        return False
    return parse_date(end) < (today or date.today()).isoformat()


EXERCISES = {
    "Strength": ["Squat", "Deadlift", "Bench Press", "Overhead Press", "Pull-Up", "Barbell Row"],
    "Hypertrophy": ["Leg Press", "Incline Dumbbell Press", "Lat Pulldown", "Lateral Raise",
                    "Bicep Curl", "Tricep Extension"],
    "Conditioning": ["Running", "Cycling", "Rowing", "Burpees", "Jump Rope",
                     "Kettlebell Swings"],
    "Full Body": ["Push-Up", "Pull-Up", "Lunge", "Plank", "Dumbbell Row", "Dumbbell Press"],
}
# level -> (sets range, reps range, training days per week)
LEVELS = {
    "beginner": ((2, 3), (8, 12), 3),
    "intermediate": ((3, 4), (8, 15), 4),
    "advanced": ((4, 5), (6, 15), 5),
}
WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def focus_for(program):
    program = program or ""
    if "Fat Loss" in program:
        return "Conditioning"
    if "Muscle Gain" in program:
        return "Hypertrophy"
    return "Full Body"


def generate_ai_program(program, experience, rng=random):
    """Build a weekly plan from the client's program focus and experience level."""
    level = LEVELS.get(str(experience).strip().lower())
    if level is None:
        raise ValueError("Invalid experience level")
    sets_range, reps_range, days = level
    pool = EXERCISES[focus_for(program)]
    per_day = 3 if days < 4 else 4
    rows = []
    for day in WEEK_DAYS[:days]:
        for exercise in rng.sample(pool, per_day):
            rows.append({"day": day, "exercise": exercise,
                         "sets": rng.randint(*sets_range), "reps": rng.randint(*reps_range)})
    return rows


def build_pdf(title, lines):
    """Render a one-page text PDF without third-party libraries."""
    def esc(text):
        text = str(text).encode("latin-1", "replace").decode("latin-1")
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = ["BT /F1 16 Tf 50 790 Td (%s) Tj ET" % esc(title)]
    y = 760
    for line in lines:
        content.append("BT /F1 12 Tf 50 %d Td (%s) Tj ET" % (y, esc(line)))
        y -= 20
    stream = "\n".join(content)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream.encode("latin-1")), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return out


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
    if conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone() is None:
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     ("admin", generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin")),
                      "Admin"))
    conn.commit()
    conn.close()


def create_app(db_path=None, rng=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or os.getenv("DB_PATH", "aceest_fitness.db")
    app.config["RNG"] = rng or random.Random()
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
        data["membership_expired"] = is_membership_expired(data.get("membership_expiry"))
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

    @app.post("/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        row = get_db().execute("SELECT password_hash, role FROM users WHERE username=?",
                               (username,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"],
                                                  str(data.get("password") or "")):
            return jsonify(error="Invalid credentials"), 401
        return jsonify(username=username, role=row["role"])

    @app.post("/clients/<name>/ai-program")
    def ai_program(name):
        row = get_db().execute("SELECT program FROM clients WHERE name=?", (name,)).fetchone()
        if row is None:
            return jsonify(error="Client not found"), 404
        experience = (request.get_json(silent=True) or {}).get("experience")
        try:
            rows = generate_ai_program(row["program"], experience, current_app.config["RNG"])
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(rows)

    @app.get("/clients/<name>/report.pdf")
    def client_report(name):
        row = get_db().execute("SELECT * FROM clients WHERE name=?", (name,)).fetchone()
        if row is None:
            return jsonify(error="Client not found"), 404
        lines = [f"{label}: {row[key] if row[key] is not None else '-'}"
                 for label, key in REPORT_FIELDS]
        pdf = build_pdf(f"ACEest Client Report - {name}", lines)
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        disposition = f'attachment; filename="{safe}_report.pdf"'
        return Response(pdf, mimetype="application/pdf",
                        headers={"Content-Disposition": disposition})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
