import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CATALOG_JSON = FIXTURES / "catalog.json"
SKILLS = FIXTURES / "skills"

if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))

# A generated handler resolves its credential through `agent.secret_scope` — the runtime it is built
# for, and the only way a per-profile secret is readable. The suite needs that package on sys.path to
# import the code it just rendered; without a Hermes install those tests skip rather than pretend.
HERMES_AGENT = Path(os.environ.get("HERMES_AGENT_HOME") or (Path.home() / ".hermes" / "hermes-agent"))
if (HERMES_AGENT / "agent" / "secret_scope.py").exists() and str(HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(HERMES_AGENT))


@pytest.fixture()
def hermes_runtime():
    """Skip when there is no Hermes install to import `agent.secret_scope` from."""
    if not (HERMES_AGENT / "agent" / "secret_scope.py").exists():
        pytest.skip("needs a Hermes install (agent.secret_scope) to import generated handlers")


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
def catalog():
    return json.loads(CATALOG_JSON.read_text())
