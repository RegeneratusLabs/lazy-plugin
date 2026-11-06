"""A generated plugin must load, register its tools, and refuse to be nonsense."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

GOOD = {
    "name": "gpu-price-watch",
    "title": "GPU Price Watch",
    "description": "Watch GPU listing pages for prices under a threshold and report the cheapest match.",
    "author": "Josh Thomson",
    "tools": [
        {"name": "check_prices", "description": "Fetch the listing page and filter by threshold.",
         "kind": "http", "params": {"max_price": "integer price ceiling"},
         "target": "https://api.example.com/prices", "behaviour": "GET the prices endpoint."},
        {"name": "last_run", "description": "Read the last stored result.", "kind": "file",
         "params": {}, "behaviour": "Read config.path."},
    ],
    "hooks": ["on_session_end"],
}

CATALOG = {"entries": []}


@pytest.fixture()
def creator(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"cr_{id(tmp_path)}", ROOT / "creator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CORE.load_catalog = lambda force=False: CATALOG
    mod.validate_plugin = lambda path, timeout=180: {"ok": True, "failures": [], "tail": ["Validation passed."]}
    return mod


def test_spec_is_cleaned_and_carries_every_tool(creator):
    clean, problems = creator.validate_spec(GOOD)
    assert problems == []
    assert clean["name"] == "gpu-price-watch"
    assert [t["name"] for t in clean["tools"]] == ["check_prices", "last_run"]
    assert clean["hooks"] == ["on_session_end"]


@pytest.mark.parametrize("bad,reason", [
    ({"name": "Bad Name!", "description": "x" * 30, "tools": [{"name": "ok_tool"}]}, "name"),
    ({"name": "fine-name", "description": "short", "tools": [{"name": "ok_tool"}]}, "description"),
    ({"name": "fine-name", "description": "x" * 30, "tools": []}, "tool"),
    ({"name": "fine-name", "description": "x" * 30,
      "tools": [{"name": "Bad-Tool"}]}, "tool name"),
    ({"name": "fine-name", "description": "x" * 30,
      "tools": [{"name": "a_tool"}, {"name": "a_tool"}]}, "duplicate"),
])
def test_bad_specs_are_refused_and_never_rendered(creator, bad, reason):
    clean, problems = creator.validate_spec(bad)
    assert clean is None
    assert any(reason in p for p in problems)


def test_unknown_handler_kind_falls_back_to_a_stub(creator):
    clean, _ = creator.validate_spec({**GOOD, "tools": [{"name": "do_it", "kind": "rm -rf"}]})
    assert clean["tools"][0]["kind"] == "stub"


def test_render_emits_manifest_init_readme_and_skill(creator):
    clean, _ = creator.validate_spec(GOOD)
    files = creator.render(clean)
    assert set(files) == {"plugin.yaml", "__init__.py", "README.md",
                          "skills/gpu-price-watch/SKILL.md"}
    assert "provides_tools:" in files["plugin.yaml"]
    assert "  - check_prices" in files["plugin.yaml"]
    assert "provides_hooks:\n  - on_session_end" in files["plugin.yaml"]
    assert "def register(ctx)" in files["__init__.py"]
    assert 'toolset=PLUGIN["name"]' in files["__init__.py"]


def test_generated_plugin_imports_and_registers_its_tools(creator, tmp_path):
    clean, _ = creator.validate_spec(GOOD)
    files = creator.render(clean)
    target = tmp_path / "gen"
    for rel, body in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    sys.path.insert(0, str(target))
    try:
        module = importlib.import_module("__init__gen_test") if False else None
        spec = importlib.util.spec_from_file_location("gen_plugin", target / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    registered = []

    class Ctx:
        def register_tool(self, **kwargs):
            registered.append(kwargs)

        def register_hook(self, name, fn):
            registered.append({"hook": name, "fn": fn})

    module.register(Ctx())
    names = [r["name"] for r in registered if "name" in r]
    assert names == ["check_prices", "last_run"]
    for entry in (r for r in registered if "name" in r):
        assert entry["schema"]["name"] == entry["name"]
        assert entry["schema"]["parameters"]["type"] == "object"
        assert callable(entry["handler"])
    assert any(r.get("hook") == "on_session_end" for r in registered)


def test_handlers_return_errors_instead_of_raising(creator, tmp_path):
    clean, _ = creator.validate_spec({**GOOD, "hooks": []})
    files = creator.render(clean)
    target = tmp_path / "gen2"
    for rel, body in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_plugin2", target / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # The template now holds a real URL, so an unset parameter is a network answer, not a raise.
    http_result = module.handle_check_prices({}, {})
    assert http_result["ok"] is False and http_result.get("error")
    file_result = module.handle_last_run({}, {})
    assert file_result["ok"] is False and "config.path" in file_result["error"]


def test_file_handler_reads_a_real_path(creator, tmp_path):
    clean, _ = creator.validate_spec({**GOOD, "hooks": [], "tools": [
        {"name": "read_it", "description": "Read a file.", "kind": "file"}]})
    files = creator.render(clean)
    target = tmp_path / "gen3"
    for rel, body in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_plugin3", target / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    target_file = tmp_path / "note.txt"
    target_file.write_text("hello", encoding="utf-8")
    result = module.handle_read_it({}, {"path": str(target_file)})
    assert result["ok"] is True and result["text"] == "hello"


def test_create_writes_to_the_outbox_and_validates(creator):
    out = creator.create(GOOD)
    assert out["ok"] is True
    bundle = Path(out["dir"])
    assert (bundle / "plugin.yaml").exists()
    assert (bundle / "skills" / "gpu-price-watch" / "SKILL.md").exists()
    assert out["validation"]["ok"] is True


def test_create_refuses_to_overwrite_a_previous_generation(creator):
    creator.create(GOOD)
    again = creator.create(GOOD)
    assert again["ok"] is False
    assert any("already exists" in p for p in again["problems"])


def test_create_refuses_a_bad_spec_without_writing(creator, tmp_path):
    out = creator.create({**GOOD, "name": "No"})
    assert out["ok"] is False and out["stage"] == "spec"
    assert not (tmp_path / "created" / "No").exists()
