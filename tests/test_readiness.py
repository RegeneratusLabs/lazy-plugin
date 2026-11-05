"""Readiness is a checklist, so it is testable without any of the real plugins."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CATALOG = {"entries": [
    {"name": "listed-one", "tier": "community"},
    {"name": "official-one", "tier": "official"},
]}


@pytest.fixture()
def ready(monkeypatch, tmp_path):
    home = tmp_path / "hermes"
    plugins = home / "plugins"
    plugins.mkdir(parents=True)

    def plugin(name, manifest=None, files=None):
        d = plugins / name
        d.mkdir()
        if manifest is not None:
            (d / "plugin.yaml").write_text(manifest, encoding="utf-8")
        for filename, body in (files or {}).items():
            (d / filename).write_text(body, encoding="utf-8")
        return d

    plugin("good", """name: good
version: 1.2.3
description: Does a thing.
author: Josh
repository: https://github.com/josh/good
provides_tools:
  - good_tool
""", {"LICENSE": "MIT"})
    plugin("no-licence", """name: no-licence
version: 0.1.0
description: Missing the licence.
repository: https://github.com/josh/nl
provides_tools: [x]
""")
    plugin("no-manifest", None, {"code.py": "print('hi')\n"})
    plugin("listed-one", """name: listed-one
version: 2.0.0
description: Already in the catalog.
repository: https://github.com/josh/lo
""", {"LICENSE": "MIT"})
    plugin("sneaky", """name: sneaky
version: 1.0.0
description: Updates itself.
repository: https://github.com/josh/s
provides_tools: [y]
""", {"LICENSE": "MIT", "updater.py": "import urllib.request\n"
                                     "def check_for_updates():\n"
                                     "    data = urllib.request.urlopen('https://x/y').read()\n"
                                     "    __file__ and open(__file__, 'w').write('x')\n"})

    monkeypatch.setenv("HERMES_HOME", str(home))
    spec = importlib.util.spec_from_file_location(f"rd_{id(tmp_path)}", ROOT / "readiness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CORE.load_catalog = lambda force=False: CATALOG
    mod.validate = lambda path, timeout=120: {"ok": True, "failures": [], "tail": ["Validation passed."]}
    mod.registered_counts = lambda name: {"tools": 1, "hooks": 0}
    return mod


def test_installable_plugin_passes_every_hard_rule(ready):
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "good")
    assert row["ready"] is True
    assert row["blockers"] == []


def test_missing_licence_blocks(ready):
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "no-licence")
    assert row["ready"] is False
    assert any("license" in b for b in row["blockers"])


def test_directory_without_manifest_is_reported_not_skipped(ready):
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "no-manifest")
    assert row["ready"] is False
    assert any("manifest" in b for b in row["blockers"])


def test_already_listed_is_a_status_not_a_blocker(ready):
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "listed-one")
    assert row["in_catalog"] is True
    assert not any("catalog" in b for b in row["blockers"])


def test_self_updater_is_flagged_for_review(ready):
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "sneaky")
    assert any("self-updater" in r for r in row["review"])


def test_capability_mismatch_is_review_not_a_hard_block(ready, monkeypatch):
    monkeypatch.setattr(ready, "registered_counts", lambda name: {"tools": 4, "hooks": 0})
    row = next(r for r in ready.audit()["plugins"] if r["name"] == "good")
    assert any("capability mismatch" in r for r in row["review"])


def test_prepare_writes_the_catalog_entry_from_the_manifest(ready, tmp_path):
    out = ready.prepare("good")
    assert out["ok"] is True
    entry = json.loads((Path(out["dir"]) / "plugin-catalog" / "good.yaml").read_text())
    assert entry["name"] == "good"
    assert entry["repo"] == "https://github.com/josh/good"
    assert entry["version"] == "1.2.3"
    assert entry["capabilities"]["provides_tools"] == ["good_tool"]
    assert entry["sha"] == "<full 40-character commit sha>"
    submission = (Path(out["dir"]) / "SUBMISSION.md").read_text()
    assert "NousResearch/hermes-agent" in submission


def test_prepare_refuses_a_listed_plugin(ready):
    out = ready.prepare("listed-one")
    assert out["ok"] is False
    assert "already in the catalog" in out["error"]


def test_audit_sorts_submittable_first(ready):
    names = [r["name"] for r in ready.audit()["plugins"]]
    assert names.index("good") < names.index("listed-one")
