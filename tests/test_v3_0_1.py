"""Unit tests for ACEest backend v3.0.1."""
from urllib.parse import quote

import pytest

from backend import app_v3_0_1 as m


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
    app = m.create_app(str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    return app.test_client()


def test_health_reports_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "version": "3.0.1"}


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


def test_log_and_list_metrics_sorted_by_date(client):
    client.post("/clients", json=payload())
    client.post("/clients/Rahul/metrics",
                json={"date": "2026-02-01", "weight": 74, "waist": 85, "bodyfat": 20})
    client.post("/clients/Rahul/metrics", json={"date": "2026-01-01", "weight": 76})
    rows = client.get("/clients/Rahul/metrics").get_json()
    assert [r["date"] for r in rows] == ["2026-01-01", "2026-02-01"]
    assert rows[1] == {"date": "2026-02-01", "weight": 74.0, "waist": 85.0, "bodyfat": 20.0}
    assert rows[0]["waist"] == 0.0


@pytest.mark.parametrize("body", [
    {}, {"date": "01-02-2026"}, {"date": "2026-01-01", "weight": -1},
    {"date": "2026-01-01", "bodyfat": 150}, {"date": "2026-01-01", "waist": "abc"}])
def test_metrics_validation(client, body):
    client.post("/clients", json=payload())
    assert client.post("/clients/Rahul/metrics", json=body).status_code == 400


def test_metrics_unknown_client(client):
    assert client.post("/clients/Ghost/metrics", json={"date": "2026-01-01"}).status_code == 404
    assert client.get("/clients/Ghost/metrics").status_code == 404


@pytest.mark.parametrize("height,weight,bmi,category", [
    (170, 50, 17.3, "Underweight"), (170, 70, 24.2, "Normal"),
    (170, 80, 27.7, "Overweight"), (170, 100, 34.6, "Obese")])
def test_calculate_bmi_categories(height, weight, bmi, category):
    result = m.calculate_bmi(height, weight)
    assert result[0] == bmi
    assert result[1] == category
    assert result[2]


def test_bmi_category_boundaries():
    assert m.calculate_bmi(100, 18.5)[1] == "Normal"
    assert m.calculate_bmi(100, 25)[1] == "Overweight"
    assert m.calculate_bmi(100, 30)[1] == "Obese"


@pytest.mark.parametrize("height,weight", [(0, 70), (170, 0), (None, 70), (170, None), (-1, 70)])
def test_calculate_bmi_rejects_missing_data(height, weight):
    with pytest.raises(ValueError):
        m.calculate_bmi(height, weight)


def test_bmi_endpoint(client):
    client.post("/clients", json=payload(height=170, weight=70))
    body = client.get("/clients/Rahul/bmi").get_json()
    assert body["bmi"] == 24.2
    assert body["category"] == "Normal"


def test_bmi_endpoint_needs_height_and_weight(client):
    client.post("/clients", json={"name": "A", "program": BG, "weight": 70})
    assert client.get("/clients/A/bmi").status_code == 400
    assert client.get("/clients/Ghost/bmi").status_code == 404


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
