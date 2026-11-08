"""The smoke test: it must catch what `plugins validate` cannot.

Each case here is a real failure that shipped from this builder: a stub body that raises, a handler
asking for a config value nothing sets, a crash, a handler that returns nothing useful. Plus the
happy path, proved against a loopback server so it exercises a real request.
"""

import http.server
import importlib.util
import json
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def smoke_mod():
    spec = importlib.util.spec_from_file_location("smoke_under_test", ROOT / "smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANIFEST = """name: {name}
version: 0.1.0
description: >-
  A fixture plugin used to prove the smoke test grades honestly.
author: Tests
provides_tools:
  - {tool}
{requires}"""


def bundle(tmp_path, name="fixture-plugin", tool="do_it", requires=None, body=None):
    root = tmp_path / name
    root.mkdir(parents=True)
    (root / "plugin.yaml").write_text(
        MANIFEST.format(name=name, tool=tool,
                        requires=f"requires_env:\n  - {requires}\n" if requires else ""),
        encoding="utf-8")
    (root / "__init__.py").write_text(body or "", encoding="utf-8")
    return root


HITS = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server names it
        HITS.append(self.path)
        payload = json.dumps({"results": [{"title": "a"}, {"title": "b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def make_http_bundle(tmp_path, base):
    body = f"""
import json, urllib.request

def handle_do_it(params, **kwargs):
    with urllib.request.urlopen({base!r} + "/search?q=cat", timeout=5) as response:
        payload = json.loads(response.read())
    return json.dumps({{"ok": True, "count": len(payload["results"]), "items": payload["results"]}})

PARAMS = {{"do_it": {{"query": "what to search for"}}}}

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture",
                      schema={{"name": "do_it", "description": "search", "parameters": {{}}}},
                      handler=handle_do_it, description="search")
"""
    return bundle(tmp_path, body=body)


@pytest.fixture()
def loopback():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_a_working_tool_is_graded_works(smoke_mod, tmp_path, loopback):
    report = smoke_mod.smoke(make_http_bundle(tmp_path, loopback), live=True)
    assert report["verdict"] == "works", report
    assert report["tools"][0]["status"] == "works"
    assert "came back with real results" in smoke_mod.headline(report)


def test_a_missing_key_is_reported_without_calling(smoke_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("FIXTURE_TOKEN", raising=False)
    body = """
def handle_do_it(params, **kwargs):
    raise AssertionError("the smoke test must not call a tool whose key is missing")

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, requires="FIXTURE_TOKEN", body=body))
    assert report["verdict"] == "needs-key"
    assert "FIXTURE_TOKEN" in smoke_mod.headline(report)


def test_a_stub_body_is_half_built_not_broken(smoke_mod, tmp_path):
    """Unfinished is not the same as failed: a green validate line above a red receipt reads as a lie."""
    body = """
def handle_do_it(params, **kwargs):
    raise NotImplementedError("This tool is a scaffold. Developer must write a parser")

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, body=body))
    assert report["verdict"] == "scaffold"
    assert "half-built" in smoke_mod.headline(report)
    assert "nothing was ever written" in smoke_mod.headline(report)


def test_a_crash_is_broken_and_names_the_error(smoke_mod, tmp_path):
    body = """
def handle_do_it(params, **kwargs):
    return {}["missing"]

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, body=body), live=True)
    assert report["verdict"] == "broken"
    assert "KeyError" in report["tools"][0]["detail"]


def test_a_plugin_that_registers_nothing_is_broken(smoke_mod, tmp_path):
    body = "def register(ctx):\n    pass\n"
    report = smoke_mod.smoke(bundle(tmp_path, body=body))
    assert report["verdict"] == "broken"
    assert any("never registered" in note or "no tools" in note for note in report["notes"])


def test_a_package_that_cannot_import_is_broken(smoke_mod, tmp_path):
    report = smoke_mod.smoke(bundle(tmp_path, body="this is not python\n"))
    assert report["verdict"] == "broken"
    assert "cannot load the package" in report["notes"][0]


def test_sample_params_are_plausible(smoke_mod):
    params = smoke_mod.sample_params({"query": "phrase", "limit": "count", "city": "place"})
    assert params["query"] == "cat nip"
    # a date or a domain answered "test" is a 404 the receipt would blame on the far end
    typed = smoke_mod.sample_params({"date": "day", "domain": "host", "email": "address"})
    assert typed["date"][:2] == "20" and typed["date"][4] == "-"
    assert typed["domain"] == "example.com" and "@" in typed["email"]
    assert params["limit"] == 3
    assert params["city"] == "Brisbane"


def test_live_false_skips_the_call(smoke_mod, tmp_path, loopback):
    report = smoke_mod.smoke(make_http_bundle(tmp_path, loopback), live=False)
    assert report["tools"][0]["status"] == "skipped"
    assert report["verdict"] == "unchecked"


def test_a_credential_is_not_carried_to_a_plain_http_host(smoke_mod, tmp_path, loopback, monkeypatch):
    """A model drafts the variable and the URL. Over plain http, the key stays home."""
    monkeypatch.setenv("FIXTURE_TOKEN", "sekrit")
    source = make_http_bundle(tmp_path, loopback)
    HITS.clear()
    keyed = bundle(tmp_path, name="keyed-fixture", requires="FIXTURE_TOKEN",
                   body=(source / "__init__.py").read_text(encoding="utf-8"))
    report = smoke_mod.smoke(keyed, live=True)
    assert report["verdict"] == "refused", report
    assert report["tools"][0]["status"] == "refused"
    assert "FIXTURE_TOKEN" in report["tools"][0]["detail"]
    assert "not https" in report["tools"][0]["detail"]
    assert HITS == [], "the refused tool still made a request"
    assert "not tried out" in smoke_mod.headline(report)


def test_a_hermes_credential_is_never_carried_anywhere(smoke_mod, tmp_path, monkeypatch):
    """Even to a public https host: the host's own provider keys are not a plugin's to spend."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    body = """
import json, urllib.request

def handle_do_it(params, **kwargs):
    with urllib.request.urlopen("https://api.example.com/v1/search?q=cat", timeout=5) as response:
        return json.dumps({"ok": True, "count": 1})

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, requires="OPENAI_API_KEY", body=body), live=True)
    assert report["verdict"] == "refused", report
    assert "Hermes' own credential" in report["tools"][0]["detail"]


def test_egress_rules_are_literal(smoke_mod):
    assert smoke_mod.egress_problem("https://api.example.com/v1") == ""
    assert "not https" in smoke_mod.egress_problem("http://api.example.com/v1")
    assert "loopback" in smoke_mod.egress_problem("https://127.0.0.1/v1") or \
        "is 127" in smoke_mod.egress_problem("https://127.0.0.1/v1")
    for host in ("https://169.254.169.254/latest/meta-data", "https://10.0.0.5/x",
                 "https://192.168.1.1/x", "https://localhost/x", "https://box.local/x",
                 "https://[::1]/x", "https://0.0.0.0/x"):
        assert smoke_mod.egress_problem(host), host
    assert smoke_mod.is_host_credential("ANTHROPIC_API_KEY")
    assert smoke_mod.is_host_credential("GITHUB_TOKEN")
    assert smoke_mod.is_host_credential("HERMES_ANYTHING")
    assert not smoke_mod.is_host_credential("BREWERYDB_API_KEY")


def test_a_write_tool_is_sampled_with_a_write(smoke_mod, tmp_path):
    """Order of the test, not the template: a write body needs write=True or it reads a missing file."""
    body = """
import json, os
from pathlib import Path

def handle_do_it(params, **kwargs):
    target = Path(os.environ["HERMES_HOME"]) / "note.txt"
    if params.get("write"):
        target.write_text(str(params.get("content") or ""), encoding="utf-8")
        return json.dumps({"ok": True, "bytes": target.stat().st_size})
    return json.dumps({"ok": True, "text": target.read_text()})

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture",
                      schema={"name": "do_it", "parameters": {"properties": {"path": {}}}},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, body=body), live=True)
    assert report["tools"][0]["status"] == "works", report
    assert report["tools"][0]["params"]["write"] is True
    assert report["tools"][0]["params"]["content"] == "lazy plugin smoke"
