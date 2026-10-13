"""Unit tests for ACEest backend v2.1.2."""
from urllib.parse import quote

import pytest

import app.app_v2_1_2 as m


FL, FL_FACTOR = "Fat Loss (FL)", 22
MG, MG_FACTOR = "Muscle Gain (MG)", 35
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
    assert r.get_json() == {"status": "ok", "version": "2.1.2"}


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
