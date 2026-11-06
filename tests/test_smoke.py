"""The smoke test: it must catch what `plugins validate` cannot.

Each case here is a real failure that shipped from this builder: a stub body that raises, a handler
asking for a config value nothing sets, a crash, a handler that returns nothing useful. Plus the
happy path, proved against a loopback server so it exercises a real request.
"""

import http.server
import importlib.util
import json
import sys
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


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server names it
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
    report = smoke_mod.smoke(make_http_bundle(tmp_path, loopback))
    assert report["verdict"] == "works", report
    assert report["tools"][0]["status"] == "works"
    assert "returned real results" in smoke_mod.headline(report)


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


def test_a_stub_body_is_broken_not_valid(smoke_mod, tmp_path):
    body = """
def handle_do_it(params, **kwargs):
    raise NotImplementedError("This tool is a scaffold. Developer must write a parser")

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, body=body))
    assert report["verdict"] == "broken"
    assert "scaffold" in smoke_mod.headline(report)


def test_a_crash_is_broken_and_names_the_error(smoke_mod, tmp_path):
    body = """
def handle_do_it(params, **kwargs):
    return {}["missing"]

def register(ctx):
    ctx.register_tool(name="do_it", toolset="fixture", schema={"name": "do_it"},
                      handler=handle_do_it, description="x")
"""
    report = smoke_mod.smoke(bundle(tmp_path, body=body))
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
    assert params["query"] == "cat"
    assert params["limit"] == 3
    assert params["city"] == "Brisbane"


def test_live_false_skips_the_call(smoke_mod, tmp_path, loopback):
    report = smoke_mod.smoke(make_http_bundle(tmp_path, loopback), live=False)
    assert report["tools"][0]["status"] == "skipped"
    assert report["verdict"] == "unchecked"
