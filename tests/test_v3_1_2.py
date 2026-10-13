"""Unit tests for ACEest backend v3.1.2."""
import random
import sqlite3
from urllib.parse import quote

import pytest

from backend import app_v3_1_2 as m


FL, FL_FACTOR = "Fat Loss (FL) – 3 day", 22
MG, MG_FACTOR = "Muscle Gain (MG) – PPL", 35
BG, BG_FACTOR = "Beginner (BG)", 26


def payload(**overrides):
    base = {"name": "Rahul", "age": 28, "height": 175, "weight": 75,
            "program": FL}
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
    assert r.get_json() == {"status": "ok", "version": "3.1.2"}


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


def test_programs_endpoint_lists_every_program(client):
    data = client.get("/programs").get_json()
    assert {p["name"] for p in data} == set(m.PROGRAMS)
    assert all(p["calorie_factor"] > 0 and p["code"] for p in data)


@pytest.mark.parametrize("program,factor", [(FL, FL_FACTOR), (MG, MG_FACTOR), (BG, BG_FACTOR)])
def test_calculate_calories_per_program(program, factor):
    assert m.calculate_calories(80, program) == int(80 * factor)


def test_calculate_calories_truncates_to_int():
    assert m.calculate_calories(72.5, FL) == int(72.5 * FL_FACTOR)


def test_calculate_calories_unknown_program():
    with pytest.raises(ValueError, match="Unknown program"):
        m.calculate_calories(70, "Nope")


@pytest.mark.parametrize("weight", [0, -5, None])
def test_calculate_calories_rejects_bad_weight(weight):
    with pytest.raises(ValueError, match="Weight must be positive"):
        m.calculate_calories(weight, BG)


def test_save_and_load_client(client):
    r = client.post("/clients", json=payload())
    assert r.status_code == 201
    assert r.get_json()["calories"] == int(75 * FL_FACTOR)
    body = client.get("/clients/Rahul").get_json()
    assert body["program"] == FL and body["weight"] == 75
    assert body["calories"] == int(75 * FL_FACTOR)
    assert "id" not in body


def test_updating_client_returns_200_and_recalculates(client):
    client.post("/clients", json=payload())
    r = client.post("/clients", json=payload(weight=80, program=MG))
    assert r.status_code == 200
    assert client.get("/clients/Rahul").get_json()["calories"] == int(80 * MG_FACTOR)


def test_client_without_weight_has_no_calories(client):
    r = client.post("/clients", json={"name": "NoWeight", "program": BG})
    assert r.status_code == 201
    assert r.get_json()["calories"] is None


def test_empty_optional_fields_are_ignored(client):
    r = client.post("/clients", json=payload(age=None, weight=""))
    assert r.status_code == 201
    assert r.get_json()["calories"] is None


@pytest.mark.parametrize("bad", [{"name": "X"}, {"program": FL}, {"name": " ", "program": FL}, {}])
def test_missing_name_or_program_rejected(client, bad):
    r = client.post("/clients", json=bad)
    assert r.status_code == 400
    assert r.get_json()["error"] == "Name and Program required"


def test_unknown_program_rejected(client):
    r = client.post("/clients", json=payload(program="Nope"))
    assert r.status_code == 400
    assert r.get_json()["error"] == "Unknown program"


@pytest.mark.parametrize("field,value", [
    ("weight", -1), ("weight", "abc"), ("age", 0), ("age", "x")])
def test_invalid_numbers_rejected(client, field, value):
    assert client.post("/clients", json=payload(**{field: value})).status_code == 400


def test_client_names_with_spaces(client):
    client.post("/clients", json=payload(name="Mary Jane"))
    assert client.get("/clients/Mary%20Jane").status_code == 200


def test_sql_injection_attempt_is_stored_literally(client):
    evil = "x'; DROP TABLE clients;--"
    assert client.post("/clients", json=payload(name=evil)).status_code == 201
    assert client.get("/clients/" + quote(evil, safe="")).get_json()["name"] == evil
    assert client.post("/clients", json=payload()).status_code == 201


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


@pytest.mark.parametrize("level,days,per_day,sets,reps", [
    ("beginner", 3, 3, (2, 3), (8, 12)), ("intermediate", 4, 4, (3, 4), (8, 15)),
    ("advanced", 5, 4, (4, 5), (6, 15))])
def test_generate_ai_program_shape(level, days, per_day, sets, reps):
    rows = m.generate_ai_program(FL, level, random.Random(1))
    assert len(rows) == days * per_day
    assert [r["day"] for r in rows][::per_day] == m.WEEK_DAYS[:days]
    assert all(sets[0] <= r["sets"] <= sets[1] and reps[0] <= r["reps"] <= reps[1]
               for r in rows)


@pytest.mark.parametrize("program,focus", [
    (FL, "Conditioning"), (MG, "Hypertrophy"), (BG, "Full Body"), (None, "Full Body")])
def test_ai_program_focus_follows_client_program(program, focus):
    rows = m.generate_ai_program(program, "beginner", random.Random(2))
    assert {r["exercise"] for r in rows} <= set(m.EXERCISES[focus])


def test_no_exercise_repeats_within_a_day():
    rows = m.generate_ai_program(MG, "advanced", random.Random(4))
    for day in m.WEEK_DAYS[:5]:
        names = [r["exercise"] for r in rows if r["day"] == day]
        assert len(names) == len(set(names))


def test_experience_level_is_case_insensitive():
    assert m.generate_ai_program(FL, " Advanced ", random.Random(1))


@pytest.mark.parametrize("bad", [None, "", "expert", 5])
def test_invalid_experience_rejected(bad):
    with pytest.raises(ValueError, match="Invalid experience level"):
        m.generate_ai_program(FL, bad)


def test_ai_program_reproducible_with_seed():
    first = m.generate_ai_program(FL, "intermediate", random.Random(3))
    assert first == m.generate_ai_program(FL, "intermediate", random.Random(3))


def test_ai_endpoint_returns_plan(client):
    client.post("/clients", json=payload())
    r = client.post("/clients/Rahul/ai-program", json={"experience": "beginner"})
    assert r.status_code == 200
    assert len(r.get_json()) == 9
    assert set(r.get_json()[0]) == {"day", "exercise", "sets", "reps"}


def test_ai_endpoint_errors(client):
    client.post("/clients", json=payload())
    assert client.post("/clients/Rahul/ai-program", json={"experience": "x"}).status_code == 400
    assert client.post("/clients/Ghost/ai-program",
                       json={"experience": "beginner"}).status_code == 404


def test_membership_date_saved_and_flagged_expired(client):
    client.post("/clients", json=payload(membership_expiry="2020-01-01"))
    body = client.get("/clients/Rahul").get_json()
    assert body["membership_expiry"] == "2020-01-01"
    assert body["membership_expired"] is True


def test_future_membership_not_expired(client):
    client.post("/clients", json=payload(membership_expiry="2999-12-31"))
    assert client.get("/clients/Rahul").get_json()["membership_expired"] is False


def test_missing_membership_date_not_expired(client):
    client.post("/clients", json=payload())
    assert client.get("/clients/Rahul").get_json()["membership_expired"] is False


def test_invalid_membership_date_rejected(client):
    assert client.post("/clients", json=payload(membership_expiry="31/12/2030")).status_code == 400


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
