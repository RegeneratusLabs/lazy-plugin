"""Regressions for the 0.9.0 audit. Each one is a defect that shipped in 0.8.x."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_audit", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PUBLISH = load("publish")
SECRETS = load("secretscan")
SMOKE = load("smoke")
CREATOR = load("creator")


# --- a spec is intent, never code -----------------------------------------------------------------

def test_description_cannot_break_out_of_the_handler_docstring(tmp_path):
    marker = tmp_path / "pwned"
    evil = 'Watches prices """ ; __import__("os").system("touch ' + str(marker) + '") ; _ = """'
    handler = CREATOR.HANDLER.format(func="handle_x", doc=repr(evil + "\n\nFetches it."),
                                     body="    return 'ok'")
    ns = {}
    exec(compile("from typing import Any\n" + handler, "handler.py", "exec"), ns)
    ns["handle_x"]({})
    assert not marker.exists(), "a description became a statement"


def test_stub_behaviour_with_a_quote_still_parses(tmp_path):
    body = CREATOR.BODIES["stub"].format(behaviour_message=repr('scaffold. say "hi" \\ ok'))
    ns = {}
    exec(compile("def f():\n" + body, "stub.py", "exec"), ns)
    try:
        ns["f"]()
    except NotImplementedError:
        pass


# --- the commit stages everything, so the scan reads everything -----------------------------------

def test_dotenv_and_key_files_are_scanned(tmp_path):
    b = tmp_path / "leak"
    (b / "node_modules" / "pkg").mkdir(parents=True)
    (b / "plugin.yaml").write_text("name: leak\nversion: 0.1.0\ndescription: d\n")
    (b / ".env.production").write_text("OPENAI_API_KEY=sk-proj-AbCdEf1234567890AbCdEf1234567890\n")
    (b / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    (b / "notes.bak").write_text('token = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"\n')
    (b / "node_modules" / "pkg" / "bundle.js").write_text('const k = "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7"\n')
    found = {f["where"] for f in SECRETS.scan_bundle(b)["findings"]}
    assert ".env.production" in found
    assert "id_rsa" in found
    assert "notes.bak" in found
    assert "node_modules/pkg/bundle.js" in found


def test_binary_files_do_not_crash_the_scan(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "plugin.yaml").write_text("name: x\n")
    (b / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    assert SECRETS.scan_bundle(b)["ok"] is True


# --- a request field is never a path ---------------------------------------------------------------

def test_install_refuses_a_traversal_name(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    out = PUBLISH.install_local(bundle, "../../escaped", plugins, lambda p: {"ok": True})
    assert out["ok"] is False
    assert not (tmp_path / "escaped").exists()


def test_install_refuses_a_name_with_a_separator(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    assert PUBLISH.install_local(bundle, "a/b", plugins, lambda p: {"ok": True})["ok"] is False


# --- generated code gets the env it declared, not the gateway's keys ------------------------------

def test_only_declared_env_names_are_read(tmp_path):
    (tmp_path / "plugin.yaml").write_text(
        "name: x\nprovides_tools:\n  - t\nrequires_env:\n  - WANTED_KEY\n")
    assert SMOKE._declared_env(tmp_path) == ["WANTED_KEY"]


def test_no_declared_env_means_nothing_passed(tmp_path):
    (tmp_path / "plugin.yaml").write_text("name: x\n")
    assert SMOKE._declared_env(tmp_path) == []
