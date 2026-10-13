"""Tests for the version-selecting WSGI entry point.

Two kinds of test live here:

* Selection logic runs against throw-away modules generated from version numbers, inside a
  throw-away package. The expected answer is computed from those numbers, not typed in.
* Real-repo tests discover whatever app/app_v*.py files exist, so adding a new version
  needs no edit to this file.
"""
import itertools
import random
import sys
from pathlib import Path

import pytest

import wsgi

REAL_DIR = Path(__file__).resolve().parent.parent / "app"
REAL_MODULES = sorted(p.stem for p in REAL_DIR.glob("app_v*.py"))

SYNTHETIC_PKG = "synthetic_app_pkg"  # never collides with the real "app" package

APP_SOURCE = (
    "from flask import Flask\n\n\n"
    "def create_app():\n"
    "    app = Flask(__name__)\n"
    "    app.config['MARK'] = __name__\n"
    "    return app\n"
)

GENERATED = list(itertools.product(range(91, 94), range(0, 12)))
random.Random(42).shuffle(GENERATED)  # fixed seed: shuffled, but the same on every run
CASES = [
    [(91, 1), (91, 2), (91, 10)],  # 10 must beat 2 (numeric, not alphabetical)
    [(91, 10), (92, 1)],           # a new major version beats any minor version
    [(91, 1, 2), (91, 1, 10)],     # three-part versions such as app_v91_1_10
    GENERATED,                     # 36 versions written in shuffled order
]


def as_name(version):
    return "app_v" + "_".join(str(part) for part in version)


def as_tuple(name):
    return tuple(int(part) for part in name.removeprefix("app_v").split("_"))


@pytest.fixture
def make_versions(tmp_path, monkeypatch):
    """Create a module for each version tuple in a temporary package and point wsgi at it."""
    package_dir = tmp_path / SYNTHETIC_PKG
    package_dir.mkdir()

    def _make(versions):
        for version in versions:
            (package_dir / f"{as_name(version)}.py").write_text(APP_SOURCE)
        monkeypatch.setattr(wsgi, "APP_DIR", package_dir)
        monkeypatch.setattr(wsgi, "PACKAGE", SYNTHETIC_PKG)
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.delenv("APP_MODULE", raising=False)

    yield _make
    for name in [n for n in sys.modules if n.split(".")[0] == SYNTHETIC_PKG]:
        del sys.modules[name]


# ---- selection logic (generated modules) ----

@pytest.mark.parametrize("versions", CASES)
def test_newest_version_is_selected(make_versions, versions):
    make_versions(versions)
    assert wsgi.module_name() == as_name(max(versions))


def test_environment_override_wins(make_versions, monkeypatch):
    make_versions([(91, 1), (92, 1)])
    monkeypatch.setenv("APP_MODULE", as_name((91, 1)))
    assert wsgi.module_name() == as_name((91, 1))


def test_empty_environment_value_falls_back_to_newest(make_versions, monkeypatch):
    make_versions([(91, 1), (92, 1)])
    monkeypatch.setenv("APP_MODULE", "")
    assert wsgi.module_name() == as_name((92, 1))


def test_missing_modules_fail_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(wsgi, "APP_DIR", tmp_path)
    monkeypatch.delenv("APP_MODULE", raising=False)
    with pytest.raises(RuntimeError):
        wsgi.module_name()


def test_create_app_loads_the_selected_module(make_versions):
    make_versions([(91, 1), (92, 3)])
    assert wsgi.create_app().config["MARK"] == f"{SYNTHETIC_PKG}.{as_name((92, 3))}"


# ---- real repository (discovered, never hard-coded) ----

def test_repo_has_at_least_one_version():
    assert REAL_MODULES, f"no app_v*.py files found in {REAL_DIR}"


def test_default_is_the_newest_real_version(monkeypatch):
    monkeypatch.delenv("APP_MODULE", raising=False)
    newest = max(as_tuple(name) for name in REAL_MODULES)
    assert wsgi.module_name() == as_name(newest)


@pytest.mark.parametrize("module", REAL_MODULES)
def test_every_real_version_serves_health(module, monkeypatch):
    monkeypatch.setenv("APP_MODULE", module)
    response = wsgi.create_app().test_client().get("/health")
    assert response.status_code == 200
