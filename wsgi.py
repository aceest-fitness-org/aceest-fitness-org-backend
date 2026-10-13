"""WSGI entry point: serve the newest app/app_v*.py, or the one named in APP_MODULE."""
import importlib
import os
import re
from pathlib import Path

PACKAGE = "app"
APP_DIR = Path(__file__).resolve().parent / PACKAGE


def _version_key(name):
    """app_v1_10 -> (1, 10), so 1.10 sorts after 1.2 and 2.1 after 1.10."""
    return tuple(int(n) for n in re.findall(r"\d+", name))


def module_name():
    chosen = os.getenv("APP_MODULE")
    if chosen:
        return chosen
    names = [p.stem for p in APP_DIR.glob("app_v*.py")]
    if not names:
        raise RuntimeError(f"No app_v*.py files found in {APP_DIR}")
    return max(names, key=_version_key)


def create_app():
    return importlib.import_module(f"{PACKAGE}.{module_name()}").create_app()