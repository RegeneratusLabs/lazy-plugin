"""Marketplace search: token scoring, identity-level evidence for installs, honest misses."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ENTRIES = [
    {"name": "market-watch", "title": "Market Watch", "category": "tools",
     "description": "Track second-hand marketplace listings and alert on new gems.",
     "docs_url": "https://github.com/a/market-watch",
     "capabilities": {"provides_tools": ["market_list", "market_watch"], "requires_env": []}},
    {"name": "hermes-finance", "title": "Finance", "category": "tools",
     "description": "Daily market brief with prices and headlines for your morning summary.",
     "repo": "https://github.com/b/finance",
     "capabilities": {"provides_tools": [], "requires_env": []}},
    {"name": "port-scanner", "title": "Port Scanner", "category": "web",
     "description": "Check open ports on a host.",
     "capabilities": {"provides_tools": [], "requires_env": ["SCAN_KEY"]}},
]


@pytest.fixture()
def mkt(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(f"mk_{id(tmp_path)}", ROOT / "marketplace.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CORE.installed_plugins = lambda: {"port-scanner"}
    mod._CORE.load_catalog = lambda force=False: {"entries": ENTRIES}
    return mod


def test_tokens_drop_stopwords_and_pluralise(mkt):
    assert mkt.tokens("Track the listings of plugins") == ["track", "listing", "plugin"]


def test_a_name_hit_beats_a_description_hit(mkt):
    hits = mkt.search("marketplace listing watch", entries=ENTRIES)
    assert hits[0]["name"] == "market-watch"
    assert hits[0]["strength"] == "strong"
    assert hits[0]["url"] == "https://github.com/a/market-watch"
    assert hits[0]["install"] == "hermes plugins install market-watch"


def test_tool_names_count_as_evidence(mkt):
    hits = mkt.search("market watch", entries=ENTRIES)
    best = hits[0]
    assert best["name"] == "market-watch"
    assert any(m["field"] in ("name", "tools") for m in best["matched"])


def test_description_only_overlap_cannot_print_an_install_line(mkt):
    hits = mkt.search("daily market brief", entries=ENTRIES)
    assert hits, "description overlap should still surface as a lead"
    assert all(h["strength"] == "possible" for h in hits)


def test_no_overlap_returns_nothing_rather_than_a_bad_guess(mkt):
    assert mkt.search("kubernetes ingress controller", entries=ENTRIES) == []


def test_generic_words_alone_do_not_match(mkt):
    assert mkt.search("plugin tool provider", entries=ENTRIES) == []


def test_falls_back_to_repo_when_no_docs_url(mkt):
    hits = mkt.search("daily brief", entries=ENTRIES)
    finance = next(h for h in hits if h["name"] == "hermes-finance")
    assert finance["url"] == "https://github.com/b/finance"


def test_installed_flag_is_reported(mkt):
    hits = mkt.search("port scanner", entries=ENTRIES)
    assert hits[0]["installed"] is True


def test_recommendation_lookup_always_offers_a_browse_link(mkt):
    found = mkt.search_for_recommendation({"title": "kubernetes ingress", "search_terms": ["ingress"]})
    assert found["best"] is None
    assert found["browse_url"].startswith("https://github.com/NousResearch/hermes-agent")
    assert found["cli_search"].startswith("hermes plugins search")
