"""ACEest Fitness & Gym - Flask backend, version 3.2.4.

Role-based login, membership status, AI-style program, workouts, PDF.
"""
import os
import random
import re
import sqlite3
from datetime import date, datetime

from flask import Flask, Response, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

VERSION = "3.2.4"

CLIENT_COLUMNS = [
    "name", "age", "height", "weight", "program", "calories", "target_weight",
    "target_adherence", "membership_status", "membership_end",
]
INT_FIELDS = ('age', 'target_adherence')
FLOAT_FIELDS = ('height', 'weight', 'target_weight')
DATE_FIELDS = ('membership_end',)
TEXT_FIELDS = ('membership_status',)
REQUIRE_PROGRAM = False
MISSING_MESSAGE = "Name is required"
REPORT_FIELDS = [
    ("Name", "name"), ("Age", "age"), ("Height", "height"), ("Weight", "weight"),
    ("Program", "program"), ("Calories", "calories"), ("Target Weight", "target_weight"),
    ("Target Adherence", "target_adherence"), ("Membership Status", "membership_status"),
    ("Membership End", "membership_end"),
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
    membership_status TEXT,
    membership_end TEXT
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


def is_membership_expired(end, today=None):
    """True when the membership end date is before today."""
    if not end:
        return False
    return parse_date(end) < (today or date.today()).isoformat()


PROGRAM_TEMPLATES = {
    "Fat Loss": ["Full Body HIIT", "Circuit Training", "Cardio + Weights"],
    "Muscle Gain": ["Push/Pull/Legs", "Upper/Lower Split", "Full Body Strength"],
    "Beginner": ["Full Body 3x/week", "Light Strength + Mobility"],
}


def generate_program(rng=random):
    """Pick a random program type and a template within it."""
    program_type = rng.choice(list(PROGRAM_TEMPLATES))
    return program_type, rng.choice(PROGRAM_TEMPLATES[program_type])


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
        return jsonify(PROGRAM_TEMPLATES)

    @app.post("/clients")
    def save_client():
        try:
            clean = parse_client(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        row = db.execute("SELECT * FROM clients WHERE name=?", (clean["name"],)).fetchone()
        merged = {**(dict(row) if row else {}), **clean}
        if not row:
            merged.setdefault("membership_status", "Active")
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
        data["membership_expired"] = is_membership_expired(data.get("membership_end"))
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
        db = get_db()
        if not client_exists(db, name):
            return jsonify(error="Client not found"), 404
        program_type, detail = generate_program(current_app.config["RNG"])
        db.execute("UPDATE clients SET program=? WHERE name=?", (detail, name))
        db.commit()
        return jsonify(program=detail, type=program_type)

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
