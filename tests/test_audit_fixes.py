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


# --- install is reversible, and uninstall is narrow ----------------------------------------------

def _linked(tmp_path, name="catnip-dealer-prices"):
    """A plugins dir with a link into an outbox bundle, the way install_local makes one."""
    home = tmp_path / "home"
    bundle = home / "lazy-plugin" / "created" / name
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text("name: x\n")
    plugins = home / "plugins"
    plugins.mkdir()
    (plugins / name).symlink_to(bundle, target_is_directory=True)
    return plugins, bundle, name


def test_uninstall_removes_the_link_it_made(tmp_path):
    plugins, bundle, name = _linked(tmp_path)
    out = PUBLISH.uninstall_local(name, plugins)
    assert out["ok"] is True
    assert not (plugins / name).exists()
    assert bundle.is_dir(), "the bundle itself must survive"


def test_uninstall_refuses_a_link_pointing_outside_the_outbox(tmp_path):
    plugins, _bundle, name = _linked(tmp_path)
    elsewhere = tmp_path / "someone-elses-plugin"
    elsewhere.mkdir()
    (plugins / name).unlink()
    (plugins / name).symlink_to(elsewhere, target_is_directory=True)
    out = PUBLISH.uninstall_local(name, plugins)
    assert out["ok"] is False
    assert "outside the outbox" in out["error"]
    assert (plugins / name).is_symlink()


def test_uninstall_refuses_a_real_directory(tmp_path):
    plugins = tmp_path / "plugins"
    (plugins / "hand-written").mkdir(parents=True)
    out = PUBLISH.uninstall_local("hand-written", plugins)
    assert out["ok"] is False
    assert (plugins / "hand-written").is_dir()


def test_uninstall_says_so_when_nothing_is_installed(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    assert PUBLISH.uninstall_local("ghost", plugins)["ok"] is False


# --- the disclosure stays a disclosure, not a dump ------------------------------------------------

def test_tokens_files_skips_working_dirs_and_caps(tmp_path):
    bundle = tmp_path / "b"
    (bundle / "desktop").mkdir(parents=True)
    (bundle / "desktop" / "plugin.js").write_text("// page\n")
    (bundle / "plugin.yaml").write_text("name: x\n")
    (bundle / "brand-drafts" / "trailer" / "out").mkdir(parents=True)
    (bundle / "brand-drafts" / "trailer" / "out" / "frames-0001.jpg").write_text("x")
    names = PUBLISH.tokens_files(bundle)
    assert "desktop/plugin.js" in names and "plugin.yaml" in names
    assert not any(name.startswith("brand-drafts/") for name in names)

    for i in range(12):
        (bundle / "bulk").mkdir(exist_ok=True)
        (bundle / "bulk" / f"f{i}.py").write_text("x")
    capped = PUBLISH.tokens_files(bundle, limit=5)
    assert len(capped) == 6
    assert capped[-1].startswith("...and")


# --- the catalog entry carries the marketplace picture -------------------------------------------

def test_catalog_entry_emits_the_pinned_banner_and_gallery(tmp_path):
    bundle = tmp_path / "lazy-plugin"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "assets" / "banner.png").write_bytes(b"png")
    (bundle / "assets" / "preview.png").write_bytes(b"png")
    entry = PUBLISH.catalog_entry(bundle, "lazy-plugin", "someone", "a" * 40,
                                  {"version": "1.0", "description": "d", "provides_tools": ["t"]})
    assert 'image: https://raw.githubusercontent.com/someone/lazy-plugin/' + "a" * 40 + "/assets/banner.png" in entry
    assert "screenshots:\n  - https://raw.githubusercontent.com/someone/lazy-plugin/" in entry
    assert "/assets/preview.png" in entry


def test_catalog_entry_without_assets_emits_no_image(tmp_path):
    bundle = tmp_path / "bare"
    bundle.mkdir()
    entry = PUBLISH.catalog_entry(bundle, "bare", "someone", "b" * 40,
                                  {"version": "1.0", "description": "d", "provides_tools": ["t"]})
    assert "image:" not in entry
    assert "screenshots: []" in entry


# --- the manifest reader works without PyYAML ----------------------------------------------------

def test_folded_description_parses_without_pyyaml(tmp_path, monkeypatch):
    import sys
    bundle = tmp_path / "p"
    bundle.mkdir()
    (bundle / "plugin.yaml").write_text(
        "name: p\nversion: 0.1.0\ndescription: >-\n  A page where you\n  describe a plugin.\n"
        "provides_tools:\n  - one\n  - two\n")
    monkeypatch.setitem(sys.modules, "yaml", None)     # makes `import yaml` raise
    manifest = CREATOR.read_manifest(bundle)
    assert manifest["description"].startswith("A page where you")
    assert manifest["description"] != ">-"
    assert manifest["provides_tools"] == ["one", "two"]
