"""A generated plugin must load, register its tools, and refuse to be nonsense."""

import importlib.util
import json
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
         "params": {}, "target": "last-run.json",
         "behaviour": "Read the stored result file."},
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


def test_an_http_tool_must_say_which_scheme(creator):
    """A bare host bakes into the handler and every call dies with 'unknown url type'."""
    spec = dict(GOOD, tools=[{"name": "find_thing", "description": "Fetch.", "kind": "http",
                              "params": {}, "request": {"url": "www.example.com.au"},
                              "behaviour": "GET the listing."}])
    clean, problems = creator.validate_spec(spec)
    assert clean is None
    assert any("scheme" in problem for problem in problems)


def test_a_declared_url_param_wins_over_the_baked_target(creator, tmp_path):
    """The caller's url must reach urllib, not be shadowed by the default the spec baked in."""
    clean, _ = creator.validate_spec({**GOOD, "hooks": [], "tools": [
        {"name": "fetch_it", "description": "Fetch.", "kind": "http",
         "params": {"url": "endpoint to fetch"},
         "request": {"url": "https://baked.invalid/never"}, "behaviour": "GET it."}]})
    files = creator.render(clean)
    target = tmp_path / "bundle"
    for rel, body in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_fetch", target / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = json.loads(module.handle_fetch_it({"url": "ftp://not-http.example"}))
    assert "ftp://not-http.example" in json.dumps(result), result
    assert "baked.invalid" not in json.dumps(result), result


@pytest.mark.parametrize("kind,needle", [("command", "target"), ("file", "target")])
def test_a_tool_with_no_target_is_refused_not_shipped_broken(creator, kind, needle):
    """A command with no argv / a file tool with no path validates but can never work."""
    spec = dict(GOOD, tools=[{"name": "do_thing", "description": "Act.", "kind": kind,
                              "params": {}, "behaviour": "Do the thing."}])
    clean, problems = creator.validate_spec(spec)
    assert clean is None
    assert any(needle in problem for problem in problems)


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


def test_generated_plugin_imports_and_registers_its_tools(creator, tmp_path, hermes_runtime):
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


def test_handlers_return_errors_instead_of_raising(creator, tmp_path, hermes_runtime):
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
    http_result = json.loads(module.handle_check_prices({}))
    assert http_result["ok"] is False and http_result.get("error")
    # A configured relative path that does not exist yet is a named error, not an exception: the
    # handler answers, and the answer says which file inside the data dir is missing.
    file_result = json.loads(module.handle_last_run({}))
    assert file_result["ok"] is False and "last-run.json" in file_result["error"]


def test_file_handler_reads_inside_its_own_data_dir(creator, tmp_path):
    """Confined, per the docstring: a generated file tool is not a reader of the host."""
    clean, _ = creator.validate_spec({**GOOD, "hooks": [], "tools": [
        {"name": "read_it", "description": "Read a file.", "kind": "file",
         "params": {"path": "file to read"}}]})
    files = creator.render(clean)
    target = tmp_path / "gen3"
    for rel, body in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_plugin3", target / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # A relative name lands in the plugin's own data dir, and HERMES_HOME decides where that is.
    written = json.loads(module.handle_read_it({"path": "note.txt", "write": True, "content": "hello"}))
    assert written["ok"] is True, written
    assert str(written["path"]).startswith(str(tmp_path / "plugin-data"))
    assert json.loads(module.handle_read_it({"path": "note.txt"}))["text"] == "hello"

    # Anything outside it is refused, read or write, relative escape or absolute path.
    outside = tmp_path / "note.txt"
    outside.write_text("host secret", encoding="utf-8")
    for attempt in ({"path": str(outside)}, {"path": "../note.txt", "write": True, "content": "x"}):
        result = json.loads(module.handle_read_it(attempt))
        assert result["ok"] is False and "outside this plugin's data dir" in result["error"], result
    assert outside.read_text(encoding="utf-8") == "host secret"


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


def test_a_file_target_on_the_host_is_refused_at_spec_time(creator):
    """The handler is confined, so an absolute target would only ever answer "outside"."""
    for target in ("/etc/passwd", "~/.hermes/.env", "C:\\Users\\josh\\secret.txt"):
        clean, problems = creator.validate_spec({**GOOD, "tools": [
            {"name": "read_it", "description": "Read a file.", "kind": "file", "target": target}]})
        assert clean is None and any("data dir" in p for p in problems), (target, problems)


def test_a_generated_plugin_may_not_declare_a_hermes_credential(creator):
    """A spec names the variable and the URL: one of Hermes' own keys must never be the variable."""
    clean, problems = creator.validate_spec({**GOOD, "tools": [
        {"name": "check_prices", "description": "Fetch prices.", "kind": "http",
         "requires_env": ["OPENAI_API_KEY"], "target": "https://api.example.com/prices"}]})
    assert clean is None
    assert any("Hermes' own credential" in p for p in problems), problems


def test_a_build_never_runs_the_code_it_generated(creator, tmp_path, monkeypatch, hermes_runtime):
    """lazyplugin_create is reachable from a model turn, so the build must not dispatch anything."""
    marker = tmp_path / "ran"
    clean, _ = creator.validate_spec({**GOOD, "name": "marker-plugin", "hooks": [], "tools": [
        {"name": "touch_marker", "description": "Write a marker file.", "kind": "command",
         "target": f"touch {marker}"}]})
    assert clean is not None

    seen = {}
    real = creator.smoke_plugin

    def spy(path, live=False):
        seen["live"] = live
        return real(path, live=live)

    monkeypatch.setattr(creator, "smoke_plugin", spy)
    out = creator.create(clean)
    assert out["ok"] is True
    assert seen == {"live": False}
    assert not marker.exists(), "the build ran a generated command"
    assert out["smoke"]["tools"][0]["status"] == "skipped"
    assert out["works"] is False
    assert "not tried out" in out["headline"]
