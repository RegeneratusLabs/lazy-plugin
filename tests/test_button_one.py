"""Button one's plumbing: the route can borrow the model, the tool degrades honestly."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLUGINSCOUT_SKILLS_DIR", str(tmp_path / "skills"))
    mod = _load(f"pc_api_{id(tmp_path)}", ROOT / "dashboard" / "plugin_api.py")
    for attr in ("_core", "_recommend_mod", "_find_ctx"):
        setattr(mod, attr, getattr(mod, attr))
    return mod


def _fake_ctx(found=True):
    ctx = SimpleNamespace(llm=SimpleNamespace())
    return (ctx if found else None), {"found": found, "reason": "plugin not loaded in this process"}


def test_post_recommend_without_ctx_tells_the_truth(api, monkeypatch):
    monkeypatch.setattr(api, "_find_ctx", lambda: _fake_ctx(False))
    import asyncio
    out = asyncio.run(api.recommend_run({"days": 7}))
    assert out["ok"] is False
    assert out["needs_llm"] is True
    assert out["fallback"] == "pluginscout_recommend"
    assert "pluginscout_recommend" in out["error"]


def test_post_recommend_runs_the_pass_when_ctx_exists(api, monkeypatch):
    monkeypatch.setattr(api, "_find_ctx", lambda: _fake_ctx(True))
    called = {}

    def fake_run(ctx, days, force):
        called.update(days=days, force=force)
        return {"ok": True, "days": days, "recommendations": [{"title": "x"}], "cached": False}

    monkeypatch.setattr(api, "_recommend_mod", lambda: SimpleNamespace(run=fake_run))
    import asyncio
    out = asyncio.run(api.recommend_run({"days": 14, "force": True}))
    assert out["ok"] is True
    assert called == {"days": 14, "force": True}


def test_post_recommend_clamps_the_window(api, monkeypatch):
    monkeypatch.setattr(api, "_find_ctx", lambda: _fake_ctx(True))
    seen = {}
    monkeypatch.setattr(api, "_recommend_mod", lambda: SimpleNamespace(
        run=lambda ctx, days, force: seen.update(days=days) or {"ok": True}))
    import asyncio
    asyncio.run(api.recommend_run({"days": 9999}))
    assert seen["days"] == 365


def test_health_reports_whether_ctx_is_reachable(api, monkeypatch):
    monkeypatch.setattr(api, "_find_ctx", lambda: _fake_ctx(False))
    import asyncio
    out = asyncio.run(api.health(probe=0))
    assert out["ctx"]["found"] is False


def test_tool_says_which_process_it_needs(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLUGINSCOUT_SKILLS_DIR", str(tmp_path / "skills"))
    tools = _load(f"pc_tools_{id(tmp_path)}", ROOT / "tools.py")
    out = json.loads(tools.handle_recommend({"days": 7}))
    assert "no ctx.llm" in out["error"]
    assert "desktop app" in out["hint"]


def test_tool_runs_when_the_plugin_published_ctx(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLUGINSCOUT_SKILLS_DIR", str(tmp_path / "skills"))
    tools = _load(f"pc_tools2_{id(tmp_path)}", ROOT / "tools.py")

    class Llm:
        def complete_structured(self, **_kw):
            return SimpleNamespace(parsed={"recommendations": []}, text="{}", provider="p",
                                   model="m", usage=None)

    published = SimpleNamespace(llm=Llm())
    holder = type(sys)("fake_plugin_module_for_test")
    holder.SCOUT_CTX = published
    sys.modules["fake_plugin_module_for_test"] = holder
    try:
        out = json.loads(tools.handle_recommend({"days": 7, "force": True}))
    finally:
        sys.modules.pop("fake_plugin_module_for_test", None)
    assert "error" in out and "no ctx.llm" not in str(out.get("error"))
    assert out.get("ok") is False  # no state.db in the fixture home, so the window is empty
