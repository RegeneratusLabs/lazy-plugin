"""The http template: a real request, with real query params, and a named error when a key is missing.

These run a loopback server, so they prove the generated code builds a URL and reads a JSON body —
the two things the old "config.url is not set" body could never do.
"""

import http.server
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def creator():
    spec = importlib.util.spec_from_file_location("creator_http", ROOT / "creator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):  # noqa: N802 - http.server names it
        _Handler.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        body = json.dumps({
            "results": [
                {"content_description": "cat one", "content_rating": "g",
                 "media_formats": {"gif": {"url": "https://example.test/1.gif"}}},
                {"content_description": "cat two", "content_rating": "g",
                 "media_formats": {"gif": {"url": "https://example.test/2.gif"}}},
            ]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def loopback():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.seen = []
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _build(creator, tmp_path, base, name="loopback-gifs"):
    spec = {
        "name": name,
        "title": "Loopback GIFs",
        "description": "Search the loopback server for cat GIFs and return titles and URLs.",
        "tools": [{
            "name": "search_gifs",
            "kind": "http",
            "description": "Search for GIFs and return titles and URLs.",
            "params": {"query": "search phrase", "limit": "how many"},
            "requires_env": ["LOOPBACK_TOKEN"],
            "request": {
                "url": base + "/v2/search",
                "query": {"q": "$query", "key": "$env:LOOPBACK_TOKEN", "limit": "$limit"},
                "defaults": {"query": "funny cat", "limit": "2"},
                "headers": {"Authorization": "Bearer $env:LOOPBACK_TOKEN"},
                "limit_param": "limit",
                "items_path": "results",
                "fields": {"title": "content_description", "url": "media_formats.gif.url"},
            },
        }],
    }
    clean, problems = creator.validate_spec(spec)
    assert problems == []
    result = creator.create(clean, outbox=tmp_path)
    assert result.get("validated") is not False
    bundle = tmp_path / name / "__init__.py"
    mod_spec = importlib.util.spec_from_file_location("gen_" + name.replace("-", "_"), bundle)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    return module


def test_query_params_env_key_and_projection(creator, tmp_path, loopback, monkeypatch, hermes_runtime):
    monkeypatch.setenv("LOOPBACK_TOKEN", "secret-value")
    module = _build(creator, tmp_path, loopback)
    out = json.loads(module.HANDLERS["search_gifs"]({"query": "cats", "limit": 2}))
    assert out["ok"] is True, out
    assert out["count"] == 2
    assert out["items"][0]["title"] == "cat one"
    assert out["items"][0]["url"] == "https://example.test/1.gif"
    seen = _Handler.seen[-1]
    assert "q=cats" in seen["path"]
    assert "key=secret-value" in seen["path"]
    assert seen["auth"] == "Bearer secret-value"


def test_a_missing_key_is_named_not_401(creator, tmp_path, loopback, monkeypatch, hermes_runtime):
    monkeypatch.delenv("LOOPBACK_TOKEN", raising=False)
    module = _build(creator, tmp_path, loopback, name="loopback-missing-key")
    out = json.loads(module.HANDLERS["search_gifs"]({}))
    assert out["ok"] is False
    assert "LOOPBACK_TOKEN is not set" in out["error"]


def test_http_tool_without_a_url_is_refused(creator):
    clean, problems = creator.validate_spec({
        "name": "no-url-here", "title": "No URL", "description": "x" * 40,
        "tools": [{"name": "do_it", "kind": "http", "description": "does it"}],
    })
    assert clean is None or not clean.get("tools")
    assert any("request.url" in problem for problem in problems)


def test_a_name_of_only_request_words_is_refused(creator):
    clean, problems = creator.validate_spec({
        "name": "find-me-me", "title": "Kitty Litter", "description": "y" * 40,
        "tools": [{"name": "do_it", "kind": "stub", "description": "does it"}],
    })
    assert clean is None or not clean.get("name") == "find-me-me"
    assert any("not just the request" in problem for problem in problems)


def test_filler_prefix_is_stripped_from_a_real_name(creator):
    clean, problems = creator.validate_spec({
        "name": "find-ebay-kitty-litter", "title": "eBay Kitty Litter",
        "description": "z" * 40,
        "tools": [{"name": "do_it", "kind": "stub", "description": "does it"}],
    })
    assert problems == []
    assert clean["name"] == "ebay-kitty-litter"
