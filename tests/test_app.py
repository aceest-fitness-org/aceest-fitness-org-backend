import pytest

from app import create_app, find_program


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_list_programs(client):
    data = client.get("/programs").get_json()
    assert {p["code"] for p in data} == {"FL", "MG", "BG"}


def test_program_by_code(client):
    r = client.get("/programs/FL")
    body = r.get_json()
    assert r.status_code == 200
    assert body["name"] == "Fat Loss (FL)"
    assert body["color"] == "#e74c3c"
    assert "2,000 kcal" in body["diet"]


def test_program_by_full_name(client):
    r = client.get("/programs/Muscle%20Gain%20(MG)")
    assert r.status_code == 200
    assert r.get_json()["code"] == "MG"


def test_program_lookup_is_case_insensitive(client):
    assert client.get("/programs/bg").status_code == 200


def test_unknown_program(client):
    r = client.get("/programs/XX")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_metrics(client):
    data = client.get("/metrics").get_json()
    assert data["capacity_users"] == 150
    assert data["break_even_members"] == 250


def test_find_program_helper():
    assert find_program("zzz") == (None, None)
    assert find_program(" fl ")[0] == "FL"