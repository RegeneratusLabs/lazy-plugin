"""Button one: digest -> LLM -> grounded recommendations -> catalog join -> cache."""

import datetime
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
CATALOG_JSON = Path(__file__).resolve().parent / "fixtures" / "catalog.json"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(f"pc_{name}_{id(object())}", ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLUGINSCOUT_SKILLS_DIR", str(tmp_path / "skills"))
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, started_at REAL)""")
    conn.execute("""CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                    content TEXT, tool_name TEXT, timestamp REAL)""")
    now = datetime.datetime.now().timestamp()
    sessions = [
        ("s_ebay", "eBay store deep-dive", now - 3600),
        ("s_laptop", "Research a $300-400 laptop", now - 7200),
        ("s_quiet", "Nothing asked here", now - 9000),
    ]
    conn.executemany("INSERT INTO sessions VALUES (?,?,?)", sessions)
    msgs = [
        (("s_ebay", "user", "Deep-dive the eBay Australia seller store 'youculbb' and report every GPU", None, now - 3600)),
        (("s_ebay", "user", "Can you navigate cash converters very well? I feel like theres hidden gems", None, now - 3500)),
        (("s_ebay", "tool", '{"output": "rtx 3060 12gb $329"}', "terminal", now - 3400)),
        (("s_ebay", "tool", '{"error": "command not found: jq"}', "terminal", now - 3300)),
        (("s_laptop", "user", "Research and recommend a $300-400 AUD lightweight laptop", None, now - 7200)),
        (("s_laptop", "tool", '{"error": null, "success": true}', "read_file", now - 7100)),
        (("s_quiet", "tool", '{"ok": true}', "read_file", now - 9000)),
    ]
    conn.executemany("INSERT INTO messages (session_id, role, content, tool_name, timestamp) "
                     "VALUES (?,?,?,?,?)", msgs)
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture()
def digest(home):
    mod = _load("digest", "digest.py")
    mod._CORE.CATALOG_URL = CATALOG_JSON.as_uri()
    return mod


@pytest.fixture()
def rec(home):
    mod = _load("recommend", "recommend.py")
    mod._CORE.CATALOG_URL = CATALOG_JSON.as_uri()
    return mod


def _fake_ctx(payload):
    class Llm:
        calls = 0

        def complete_structured(self, **_kw):
            Llm.calls += 1
            return SimpleNamespace(parsed=payload, text=json.dumps(payload), provider="fake",
                                   model="fake-model", usage=SimpleNamespace(total_tokens=101, cost_usd=0.001))

    return SimpleNamespace(llm=Llm())


PAYLOAD = {
    "recommendations": [
        {
            "title": "marketplace listing intel",
            "job": "Track and summarise second-hand marketplace listings",
            "why_plugin": "needs persistence and a scheduled sweep, not a one-off shell call",
            "search_terms": ["marketplace", "listing"],
            "evidence": [
                {"session_id": "s_ebay", "quote": "Deep-dive the eBay Australia seller store"},
                {"session_id": "s_ebay", "quote": "navigate cash converters very well"},
            ],
        },
        {
            "title": "invented thing",
            "job": "hallucinated",
            "why_plugin": "no evidence",
            "search_terms": ["nonsense"],
            "evidence": [{"session_id": "s_missing", "quote": "this never happened"}],
        },
        {
            "title": "quote not in log",
            "job": "x",
            "why_plugin": "y",
            "search_terms": ["z"],
            "evidence": [{"session_id": "s_laptop", "quote": "I demand a free pony"}],
        },
    ]
}


# ---- digest

def test_digest_carries_asks_tools_and_real_failures(digest):
    d = digest.build_digest(days=7)
    ids = [s["id"] for s in d["sessions"]]
    assert "s_ebay" in ids and "s_laptop" in ids
    assert "s_quiet" not in ids, "session with no user messages is not intent"
    ebay = next(s for s in d["sessions"] if s["id"] == "s_ebay")
    assert any("youculbb" in a for a in ebay["asks"])
    assert ebay["tools"]["terminal"] == 2
    assert any("jq" in f for f in ebay["failures"])
    assert "command not found: jq" in d["text"]
    laptop = next(s for s in d["sessions"] if s["id"] == "s_laptop")
    assert laptop["failures"] == [], "error:null is not a failure"
    assert d["stats"]["sessions"] == 2


def test_digest_respects_the_char_budget(digest):
    d = digest.build_digest(days=7, char_budget=200)
    assert d["stats"]["chars"] <= 260
    assert d["stats"]["truncated"] is True
    assert len(d["sessions"]) < 2


def test_digest_without_state_db_says_so(digest, tmp_path):
    (tmp_path / "state.db").unlink()
    d = digest.build_digest(days=7)
    assert d["sessions"] == []
    assert "state.db" in d["stats"]["error"]


def test_digest_window_excludes_older_sessions(digest, home):
    conn = sqlite3.connect(home / "state.db")
    old = datetime.datetime.now().timestamp() - 30 * 86400
    conn.execute("INSERT INTO sessions VALUES ('s_old','old chat',?)", (old,))
    conn.execute("INSERT INTO messages (session_id, role, content, tool_name, timestamp) "
                 "VALUES ('s_old','user','ancient question',NULL,?)", (old,))
    conn.commit()
    conn.close()
    assert "s_old" not in [s["id"] for s in digest.build_digest(days=7)["sessions"]]
    assert "s_old" in [s["id"] for s in digest.build_digest(days=60)["sessions"]]


# ---- grounding

def test_ground_drops_invented_sessions_and_quotes(rec, digest):
    d = digest.build_digest(days=7)
    kept, dropped = rec.ground(PAYLOAD, d)
    assert [r["title"] for r in kept] == ["marketplace listing intel"]
    reasons = {x["title"]: x["reason"] for x in dropped}
    assert "invented thing" in reasons
    assert "unknown session" in reasons["invented thing"]
    assert "quote not in digest" in reasons["quote not in log"]


def test_ground_counts_distinct_sessions_not_quotes(rec, digest):
    d = digest.build_digest(days=7)
    kept, _ = rec.ground(PAYLOAD, d)
    assert kept[0]["occurrences"] == 1, "two quotes from one session is one occurrence"
    assert kept[0]["evidence_strength"] == "single-session"


def test_ground_marks_recurring_across_two_sessions(rec, digest):
    d = digest.build_digest(days=7)
    payload = {"recommendations": [{
        "title": "two sessions", "job": "j", "why_plugin": "w", "search_terms": ["x"],
        "evidence": [
            {"session_id": "s_ebay", "quote": "Deep-dive the eBay Australia seller store"},
            {"session_id": "s_laptop", "quote": "Research and recommend a $300-400 AUD lightweight laptop"},
        ]}]}
    kept, _ = rec.ground(payload, d)
    assert kept[0]["occurrences"] == 2
    assert kept[0]["evidence_strength"] == "recurring"


# ---- catalog join

def test_enrich_gives_an_install_command_or_says_none(rec, catalog):
    recs = [{"title": "a", "search_terms": ["ethics"], "catalog_matches": None},
            {"title": "b", "search_terms": ["no-such-plugin-anywhere"], "catalog_matches": None}]
    out = rec.enrich(recs)
    assert out[0]["fix"]["kind"] in ("install", "installed")
    assert out[0]["catalog_matches"], "fixture catalog has an ethics entry"
    assert out[1]["fix"]["kind"] == "none"
    assert "candidate" in out[1]["fix"]["note"]


def test_related_is_labelled_not_an_install(rec):
    # Terms that appear only in the description, twice, and nowhere in the id: a weak match.
    entries = [{"id": "agentmemory", "name": "AgentMemory", "category": "storage",
                "description": "Daemon supervisor wiring a daemon into recall",
                "capabilities": {"provides_tools": []}}]
    matches, related = rec.match_catalog({"search_terms": ["daemon", "supervisor"]}, entries, set())
    assert not matches
    assert related and related[0]["matched_on"] == "description"
    rec._catalog_index = lambda: (entries, set())
    out = rec.enrich([{"title": "r", "search_terms": ["daemon", "supervisor"]}])
    assert out[0]["fix"]["kind"] == "related"
    assert "closest: agentmemory" in out[0]["fix"]["note"]


def test_tool_and_category_hits_are_related_not_install(rec):
    """A tool name is a lead, not proof: only an id/name hit may print an install command."""
    entries = [{"id": "artifact-relay", "name": "artifact-relay", "category": "tools",
                "description": "", "capabilities": {"provides_tools": ["publish"]}}]
    rec._catalog_index = lambda: (entries, set())
    out = rec.enrich([{"title": "r", "search_terms": ["publish"]}])
    assert out[0]["fix"]["kind"] == "related"
    assert "artifact-relay (tools)" in out[0]["fix"]["note"]

    by_category = [{"id": "vault-cache", "name": "VaultCache", "category": "memory",
                    "description": "", "capabilities": {"provides_tools": []}}]
    rec._catalog_index = lambda: (by_category, set())
    out = rec.enrich([{"title": "r", "search_terms": ["memory"]}])
    assert out[0]["fix"]["kind"] == "related"
    assert "vault-cache (category)" in out[0]["fix"]["note"]


def test_id_hit_still_earns_an_install(rec):
    entries = [{"id": "marketplace-watch", "name": "marketplace-watch", "category": "tools",
                "description": "", "capabilities": {"provides_tools": []}}]
    rec._catalog_index = lambda: (entries, set())
    out = rec.enrich([{"title": "r", "search_terms": ["marketplace"]}])
    assert out[0]["fix"]["kind"] == "install"
    assert out[0]["fix"]["command"] == "hermes plugins install marketplace-watch"


# ---- run + cache

def test_run_end_to_end_and_cached(rec, digest):
    ctx = _fake_ctx(PAYLOAD)
    first = rec.run(ctx, days=7)
    assert first["ok"] is True
    assert first["cached"] is False
    assert [r["title"] for r in first["recommendations"]] == ["marketplace listing intel"]
    assert first["llm"]["model"] == "fake-model"
    assert first["dropped"], "the two bad recs are reported, not hidden"

    second = rec.run(ctx, days=7)
    assert second["cached"] is True
    assert ctx.llm.calls == 1, "second press must not spend tokens"

    third = rec.run(ctx, days=7, force=True)
    assert third["cached"] is False
    assert ctx.llm.calls == 2


def test_run_survives_a_broken_model(rec):
    class Boom:
        def complete_structured(self, **_kw):
            raise RuntimeError("provider 502")

    out = rec.run(SimpleNamespace(llm=Boom()), days=7)
    assert out["ok"] is False
    assert "provider 502" in out["error"]


def test_run_handles_unparseable_answer(rec):
    class NoJson:
        def complete_structured(self, **_kw):
            return SimpleNamespace(parsed=None, text="I think you should use Notion", provider="p",
                                   model="m", usage=None)

    out = rec.run(SimpleNamespace(llm=NoJson()), days=7)
    assert out["ok"] is False
    assert "no parseable JSON" in out["error"]
    assert "Notion" in out["raw"]


def test_run_with_empty_window_does_not_call_the_model(rec, home):
    conn = sqlite3.connect(home / "state.db")
    conn.execute("UPDATE sessions SET started_at = started_at - ?", (30 * 86400,))
    conn.commit()
    conn.close()
    ctx = _fake_ctx(PAYLOAD)
    out = rec.run(ctx, days=1, force=True)
    assert out["ok"] is False
    assert "no sessions" in out["error"]
    assert ctx.llm.calls == 0
