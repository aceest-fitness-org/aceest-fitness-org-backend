"""Unit tests for ACEest backend v3.2.4."""
import random
import sqlite3

import pytest

import app.app_v3_2_4 as m


DEFAULT_PROGRAM = "Push/Pull/Legs"


def payload(**overrides):
    base = {"name": "Rahul", "age": 28, "height": 175, "weight": 75,
            "program": DEFAULT_PROGRAM}
    base.update(overrides)
    return base


@pytest.fixture
def client(tmp_path):
    app = m.create_app(str(tmp_path / "test.db"), rng=random.Random(7))
    app.config["TESTING"] = True
    return app.test_client()


def test_health_reports_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "version": "3.2.4"}


def test_cors_headers_present(client):
    assert client.get("/health").headers["Access-Control-Allow-Origin"] == "*"


def test_non_json_body_rejected(client):
    r = client.post("/clients", data="x", content_type="text/plain")
    assert r.status_code == 400


def test_unknown_client_returns_404(client):
    assert client.get("/clients/Ghost").status_code == 404


def test_to_number_rules():
    assert m.to_number("5", "x", int) == 5
    for bad in ("abc", None, True, -1):
        with pytest.raises(ValueError):
            m.to_number(bad, "x")
    with pytest.raises(ValueError):
        m.to_number(0, "x", positive=True)
    with pytest.raises(ValueError):
        m.to_number(101, "x", int, maximum=100)


def test_parse_date_normalises_and_rejects():
    assert m.parse_date(" 2026-03-01 ") == "2026-03-01"
    for bad in ("01-03-2026", "2026-13-01", "", "tomorrow"):
        with pytest.raises(ValueError):
            m.parse_date(bad)


def test_week_label_format():
    from datetime import datetime
    assert m.week_label(datetime(2026, 1, 15)) == "Week 02 - 2026"


def test_save_progress(client):
    client.post("/clients", json=payload())
    r = client.post("/clients/Rahul/progress", json={"adherence": 85})
    assert r.status_code == 201
    assert r.get_json()["week"].startswith("Week ")


@pytest.mark.parametrize("value", [0, 100])
def test_progress_boundaries_accepted(client, value):
    client.post("/clients", json=payload())
    assert client.post("/clients/Rahul/progress", json={"adherence": value}).status_code == 201


@pytest.mark.parametrize("value", [-1, 101, "x", 50.5, True, None])
def test_progress_invalid_adherence_rejected(client, value):
    client.post("/clients", json=payload())
    assert client.post("/clients/Rahul/progress", json={"adherence": value}).status_code == 400


def test_progress_for_unknown_client(client):
    assert client.post("/clients/Ghost/progress", json={"adherence": 50}).status_code == 404


def test_progress_history_in_order(client):
    client.post("/clients", json=payload())
    for value in (40, 60, 80):
        client.post("/clients/Rahul/progress", json={"adherence": value})
    rows = client.get("/clients/Rahul/progress").get_json()
    assert [r["adherence"] for r in rows] == [40, 60, 80]
    assert all(r["week"].startswith("Week ") for r in rows)


def test_progress_history_empty_for_new_client(client):
    client.post("/clients", json=payload())
    assert client.get("/clients/Rahul/progress").get_json() == []


def test_progress_history_unknown_client(client):
    assert client.get("/clients/Ghost/progress").status_code == 404


def test_extended_fields_saved(client):
    client.post("/clients", json=payload(target_weight=70, target_adherence=90))
    body = client.get("/clients/Rahul").get_json()
    assert body["height"] == 175
    assert body["target_weight"] == 70
    assert body["target_adherence"] == 90


@pytest.mark.parametrize("field,value", [
    ("height", -1), ("target_weight", 0), ("target_adherence", 101)])
def test_extended_field_validation(client, field, value):
    assert client.post("/clients", json=payload(**{field: value})).status_code == 400


def test_list_clients_sorted(client):
    for name in ("Zed", "Amy", "Mia"):
        client.post("/clients", json=payload(name=name))
    assert client.get("/clients").get_json() == ["Amy", "Mia", "Zed"]


def test_list_clients_empty(client):
    assert client.get("/clients").get_json() == []


def workout(**overrides):
    base = {"date": "2026-03-01", "workout_type": "Strength", "duration_min": 45,
            "notes": "Heavy day"}
    base.update(overrides)
    return base


def test_log_workout_with_exercise(client):
    client.post("/clients", json=payload())
    exercise = {"name": "Squat", "sets": 5, "reps": 5, "weight": 100}
    assert client.post("/clients/Rahul/workouts",
                       json=workout(exercise=exercise)).status_code == 201
    rows = client.get("/clients/Rahul/workouts").get_json()
    assert rows[0]["workout_type"] == "Strength"
    assert rows[0]["duration_min"] == 45
    assert rows[0]["exercises"] == [{"name": "Squat", "sets": 5, "reps": 5, "weight": 100.0}]


def test_workout_without_exercise_has_empty_list(client):
    client.post("/clients", json=payload())
    client.post("/clients/Rahul/workouts", json=workout())
    assert client.get("/clients/Rahul/workouts").get_json()[0]["exercises"] == []


def test_workouts_listed_newest_first(client):
    client.post("/clients", json=payload())
    for day, note in (("2026-01-01", "a"), ("2026-03-01", "b"), ("2026-03-01", "c")):
        client.post("/clients/Rahul/workouts", json=workout(date=day, notes=note))
    assert [w["notes"] for w in client.get("/clients/Rahul/workouts").get_json()] == \
        ["c", "b", "a"]


@pytest.mark.parametrize("body", [
    {}, {"date": "2026-03-01"}, {"workout_type": "Strength"}, workout(date="03/01/2026"),
    workout(duration_min=-5), workout(duration_min="abc"), workout(exercise={"sets": 3}),
    workout(exercise="Squat"), workout(exercise={"name": "Squat", "sets": 0})])
def test_workout_validation(client, body):
    client.post("/clients", json=payload())
    assert client.post("/clients/Rahul/workouts", json=body).status_code == 400


def test_workout_unknown_client(client):
    assert client.post("/clients/Ghost/workouts", json=workout()).status_code == 404
    assert client.get("/clients/Ghost/workouts").status_code == 404


def test_login_success(client):
    r = client.post("/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    assert r.get_json() == {"username": "admin", "role": "Admin"}


@pytest.mark.parametrize("creds", [
    {"username": "admin", "password": "wrong"}, {"username": "ghost", "password": "x"},
    {"username": "admin"}, {}])
def test_login_rejected(client, creds):
    r = client.post("/login", json=creds)
    assert r.status_code == 401
    assert r.get_json()["error"] == "Invalid credentials"


def test_passwords_are_hashed(tmp_path):
    db = str(tmp_path / "t.db")
    m.create_app(db, rng=random.Random(7))
    stored = sqlite3.connect(db).execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored != "admin"


def test_default_admin_seeded_once(tmp_path):
    db = str(tmp_path / "t.db")
    m.create_app(db, rng=random.Random(7))
    m.create_app(db, rng=random.Random(7))
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_admin_password_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    c = m.create_app(str(tmp_path / "t.db"), rng=random.Random(7)).test_client()
    assert c.post("/login", json={"username": "admin", "password": "s3cret"}).status_code == 200
    assert c.post("/login", json={"username": "admin", "password": "admin"}).status_code == 401


def test_membership_date_saved_and_flagged_expired(client):
    client.post("/clients", json=payload(membership_end="2020-01-01"))
    body = client.get("/clients/Rahul").get_json()
    assert body["membership_end"] == "2020-01-01"
    assert body["membership_expired"] is True


def test_future_membership_not_expired(client):
    client.post("/clients", json=payload(membership_end="2999-12-31"))
    assert client.get("/clients/Rahul").get_json()["membership_expired"] is False


def test_missing_membership_date_not_expired(client):
    client.post("/clients", json=payload())
    assert client.get("/clients/Rahul").get_json()["membership_expired"] is False


def test_invalid_membership_date_rejected(client):
    assert client.post("/clients", json=payload(membership_end="31/12/2030")).status_code == 400


def test_is_membership_expired_helper():
    from datetime import date
    assert m.is_membership_expired("2026-01-01", date(2026, 1, 2)) is True
    assert m.is_membership_expired("2026-01-02", date(2026, 1, 2)) is False
    assert m.is_membership_expired(None) is False


def test_build_pdf_structure():
    pdf = m.build_pdf("Title", ["Line (one)", "Back \\ slash"])
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"Title" in pdf


def test_build_pdf_xref_offset_is_correct():
    pdf = m.build_pdf("Title", ["a"])
    offset = int(pdf.split(b"startxref\n")[1].split()[0])
    assert pdf[offset:offset + 4] == b"xref"


def test_report_endpoint_returns_pdf(client):
    client.post("/clients", json=payload())
    r = client.get("/clients/Rahul/report.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF") and b"Rahul" in r.data
    assert "Rahul_report.pdf" in r.headers["Content-Disposition"]


def test_report_filename_is_sanitised(client):
    client.post("/clients", json=payload(name="A (B)"))
    r = client.get("/clients/A%20(B)/report.pdf")
    assert r.status_code == 200
    assert 'filename="A__B__report.pdf"' in r.headers["Content-Disposition"]


def test_report_unknown_client(client):
    assert client.get("/clients/Ghost/report.pdf").status_code == 404


def test_free_text_program_not_validated_and_no_calories(client):
    r = client.post("/clients", json={"name": "Sam", "program": "Anything goes", "weight": 70})
    assert r.status_code == 201
    assert r.get_json()["calories"] is None


def test_add_client_by_name_only_is_active(client):
    assert client.post("/clients", json={"name": "Newbie"}).status_code == 201
    body = client.get("/clients/Newbie").get_json()
    assert body["membership_status"] == "Active"
    assert body["program"] is None


def test_name_only_post_does_not_overwrite_existing(client):
    client.post("/clients", json=payload(membership_status="Inactive"))
    assert client.post("/clients", json={"name": "Rahul"}).status_code == 200
    body = client.get("/clients/Rahul").get_json()
    assert body["program"] == DEFAULT_PROGRAM
    assert body["membership_status"] == "Inactive"


def test_name_is_required(client):
    r = client.post("/clients", json={})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Name is required"


def test_generate_program_unit():
    program_type, detail = m.generate_program(random.Random(5))
    assert detail in m.PROGRAM_TEMPLATES[program_type]


def test_programs_endpoint_lists_templates(client):
    assert client.get("/programs").get_json() == m.PROGRAM_TEMPLATES


def test_ai_endpoint_sets_program(client):
    client.post("/clients", json=payload())
    body = client.post("/clients/Rahul/ai-program", json={}).get_json()
    assert body["program"] in m.PROGRAM_TEMPLATES[body["type"]]
    assert client.get("/clients/Rahul").get_json()["program"] == body["program"]


def test_ai_endpoint_reproducible_with_seed(tmp_path):
    results = []
    for n in range(2):
        c = m.create_app(str(tmp_path / f"{n}.db"), rng=random.Random(11)).test_client()
        c.post("/clients", json={"name": "A"})
        results.append(c.post("/clients/A/ai-program", json={}).get_json())
    assert results[0] == results[1]


def test_ai_endpoint_unknown_client(client):
    assert client.post("/clients/Ghost/ai-program", json={}).status_code == 404
