"""Editing a generated plugin from the page: safe paths, and a validator verdict on save."""

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
    (bundle / "skills" / "gpu-price-watch").mkdir(parents=True)
    (bundle / "plugin.yaml").write_text("name: gpu-price-watch\nversion: 0.1.0\n", encoding="utf-8")
    (bundle / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    (bundle / "skills" / "gpu-price-watch" / "SKILL.md").write_text("# watch\n", encoding="utf-8")
    (bundle / "bin").mkdir()
    (bundle / "bin" / "tool.bin").write_bytes(b"\x00\x01")

    cs = importlib.util.spec_from_file_location(f"creator_{id(tmp_path)}", ROOT / "creator.py")
    creator = importlib.util.module_from_spec(cs)
    cs.loader.exec_module(creator)
    creator.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [], "tail": ["Validation passed."]}
    mod._creator_mod = lambda: creator
    return mod, bundle


def test_files_lists_editable_paths_only(api):
    mod, _ = api
    out = mod._created_files("gpu-price-watch")
    paths = [f["path"] for f in out["files"]]
    assert "plugin.yaml" in paths and "__init__.py" in paths
    assert "skills/gpu-price-watch/SKILL.md" in paths
    assert "bin/tool.bin" not in paths


def test_read_returns_content(api):
    mod, _ = api
    out = mod._read_created_file("gpu-price-watch", "plugin.yaml")
    assert out["ok"] is True and "gpu-price-watch" in out["content"]


def test_write_lands_then_revalidates(api):
    mod, bundle = api
    out = mod._write_created_file("gpu-price-watch", "skills/gpu-price-watch/SKILL.md", "# edited\n")
    assert out["ok"] is True and out["validated"] is True
    assert (bundle / "skills" / "gpu-price-watch" / "SKILL.md").read_text() == "# edited\n"
    assert out["validation"]["tail"] == ["Validation passed."]


@pytest.mark.parametrize("bad", ["../../../../etc/passwd", "/etc/passwd", "../../outside.txt"])
def test_escaping_the_bundle_is_refused(api, bad):
    """A relative path that resolves outside the outbox must never be read or written."""
    mod, bundle = api
    assert mod._read_created_file("gpu-price-watch", bad)["ok"] is False
    assert mod._write_created_file("gpu-price-watch", bad, "x")["ok"] is False
    outside = bundle.parent / "outside.txt"
    assert not outside.exists()


def test_unknown_plugin_and_binary_suffix_are_refused(api):
    mod, _ = api
    assert mod._read_created_file("nope", "plugin.yaml")["ok"] is False
    assert mod._write_created_file("gpu-price-watch", "bin/tool.bin", "x")["ok"] is False
