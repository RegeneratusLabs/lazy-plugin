import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CATALOG_JSON = FIXTURES / "catalog.json"
SKILLS = FIXTURES / "skills"

if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))


def load_core(monkeypatch, tmp_path, url: str | None = None):
    """Fresh core module pointed at the fixture catalog + fixture skills, offline."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LAZY_PLUGIN_SKILLS_DIR", str(SKILLS))
    monkeypatch.delenv("LAZY_PLUGIN_CATALOG_DIR", raising=False)
    spec = importlib.util.spec_from_file_location(f"lazyplugin_core_{id(tmp_path)}", ROOT / "core.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CATALOG_URL = url or CATALOG_JSON.as_uri()
    mod.FETCH_TIMEOUT = 5
    return mod


@pytest.fixture()
def core(monkeypatch, tmp_path):
    return load_core(monkeypatch, tmp_path)


@pytest.fixture()
def hooks(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("LAZY_PLUGIN_SKILLS_DIR", str(SKILLS))
    spec = importlib.util.spec_from_file_location(f"lazyplugin_hooks_{id(tmp_path)}", ROOT / "hooks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.core.CATALOG_URL = CATALOG_JSON.as_uri()
    return mod


@pytest.fixture()
def catalog():
    return json.loads(CATALOG_JSON.read_text())
