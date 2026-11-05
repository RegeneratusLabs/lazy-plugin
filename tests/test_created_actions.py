"""Install and share, on a generated plugin. Nothing here needs a model or the network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"api_{id(tmp_path)}", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bundle = tmp_path / "lazy-plugin" / "created" / "gpu-price-watch"
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text(
        "name: gpu-price-watch\nversion: 1.2.0\ndescription: Watch GPU prices.\n"
        "provides_tools:\n  - check_prices\n", encoding="utf-8")
    (bundle / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")

    cs = importlib.util.spec_from_file_location(f"creator_{id(tmp_path)}", ROOT / "creator.py")
    creator = importlib.util.module_from_spec(cs)
    cs.loader.exec_module(creator)
    creator.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [],
                                                         "tail": ["Validation passed."]}
    mod._creator_mod = lambda: creator
    return mod


def test_install_links_the_generated_plugin(api, tmp_path):
    out = api._install_created("gpu-price-watch")
    assert out["ok"] is True
    link = tmp_path / "plugins" / "gpu-price-watch"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / "lazy-plugin" / "created" / "gpu-price-watch").resolve()
    assert "enable" in out["next"]


def test_install_refuses_to_clobber_an_existing_plugin(api):
    api._install_created("gpu-price-watch")
    again = api._install_created("gpu-price-watch")
    assert again["ok"] is False and "already exists" in again["error"]


def test_install_refuses_a_package_that_does_not_validate(api, monkeypatch):
    monkeypatch.setattr(api, "_creator_mod",
                        lambda: type("C", (), {"validate_plugin": staticmethod(
                            lambda path, timeout=180: {"ok": False, "failures": ["✗ boom"], "tail": []})}))
    out = api._install_created("gpu-price-watch")
    assert out["ok"] is False and "does not validate" in out["error"]


def test_install_rejects_an_unknown_name(api):
    assert api._install_created("nope")["ok"] is False


def test_create_returns_a_job_and_reports_progress(api, monkeypatch):
    """The model call outlives the request: POST hands back a job, the page polls it."""
    import asyncio
    import time

    seen = []

    class Creator:
        @staticmethod
        def validate_plugin(path, timeout=180):
            return {"ok": True, "failures": [], "tail": ["Validation passed."]}

        @staticmethod
        def source_context(core, kind, name):
            seen.append((kind, name))
            return "SKILL x"

        @staticmethod
        def draft_spec(idea, llm, context=""):
            seen.append(("draft", context))
            return {"ok": True, "stage": "drafted", "spec": {"name": "x"}, "meta": {"lane": "chat"}}

        @staticmethod
        def create(spec):
            return {"ok": True, "stage": "written", "name": "x", "validation": {"ok": True, "tail": []}}

    monkeypatch.setattr(api, "_creator_mod", lambda: Creator)
    monkeypatch.setattr(api, "_find_ctx", lambda: (None, {}))

    start = asyncio.run(api.create_plugin({"idea": "watch gpu prices", "source_kind": "skill",
                                           "source_name": "chinese-marketplace-sourcing"}))
    assert start["ok"] is True and start["job"]

    state = {}
    deadline = time.time() + 10
    while time.time() < deadline:
        state = asyncio.run(api.create_job(start["job"]))
        if state.get("ok") is not None:
            break
        time.sleep(0.02)

    assert state["stage"] == "done" and state["ok"] is True
    assert state["result"]["validation"]["ok"] is True
    assert ("skill", "chinese-marketplace-sourcing") in seen


def test_create_job_rejects_an_unknown_id(api):
    import asyncio
    assert asyncio.run(api.create_job("nope"))["stage"] == "gone"


def test_share_writes_the_catalog_entry_and_a_tarball(api):
    out = api._share_created("gpu-price-watch")
    assert out["ok"] is True
    entry = Path(out["catalog_entry"])
    assert entry.exists() and entry.name == "gpu-price-watch.yaml"
    body = entry.read_text()
    assert '"version": "1.2.0"' in body
    assert '"check_prices"' in body
    assert Path(out["submission"]).exists()
    assert out["tarball"] and Path(out["tarball"]).exists()
