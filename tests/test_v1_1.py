"""Unit tests for ACEest backend v1.1."""

import pytest

from backend import app_v1_1 as m


@pytest.fixture
def client():
    app = m.create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health_reports_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "version": "1.1"}


def test_cors_headers_present(client):
    assert client.get("/health").headers["Access-Control-Allow-Origin"] == "*"


def test_programs_list_has_all_three(client):
    data = client.get("/programs").get_json()
    assert {p["code"] for p in data} == {"FL", "MG", "BG"}
    assert all({"name", "color", "calorie_factor"} <= set(p) for p in data)


@pytest.mark.parametrize("code,factor,color", [
    ("FL", 22, "#e74c3c"), ("MG", 35, "#2ecc71"), ("BG", 26, "#3498db")])
def test_program_detail(client, code, factor, color):
    body = client.get(f"/programs/{code}").get_json()
    assert body["calorie_factor"] == factor
    assert body["color"] == color
    assert body["workout"] and body["diet"]


def test_program_lookup_by_full_name_and_case(client):
    assert client.get("/programs/Muscle%20Gain%20(MG)").status_code == 200
    assert client.get("/programs/bg").get_json()["code"] == "BG"


def test_unknown_program_returns_404(client):
    r = client.get("/programs/XX")
    assert r.status_code == 404
    assert r.get_json()["error"] == "Program not found"


def test_find_program_helper():
    assert m.find_program(" fl ")[0] == "FL"
    assert m.find_program("nope") == (None, None)


def test_calorie_estimate_matches_desktop_formula(client):
    """The UI multiplies weight by calorie_factor; 75 kg Fat Loss gives 1650 kcal."""
    factor = client.get("/programs/FL").get_json()["calorie_factor"]
    assert int(75 * factor) == 1650


def test_plans_contain_calorie_targets(client):
    assert "2000" in client.get("/programs/FL").get_json()["diet"]
    assert "3200" in client.get("/programs/MG").get_json()["diet"]
