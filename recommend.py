"""The LLM pass: read a digest of real sessions, propose plugin-shaped opportunities, ground them.

Two rules make this honest, and both are enforced in code rather than asked for in the prompt:

1. **Every quote must appear in the digest.** A recommendation whose evidence cannot be found in
   the input is dropped, not softened.
2. **Every session id must exist in the digest.** Invented citations are dropped with a reason.

The catalog join then says either "install this" or "nothing in the catalog covers this" — the
second is a real finding, not a failure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")
_DIGEST = _load("digest", "digest.py")

PROMPT_VERSION = "scout-recommend-v1"
CACHE_TTL_SECONDS = 12 * 3600
MAX_RECOMMENDATIONS = 5

SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short name for the plugin, 2-5 words."},
                    "job": {"type": "string", "description": "The recurring job it does, one sentence."},
                    "why_plugin": {"type": "string",
                                   "description": "Why this needs a plugin (hooks, persistence, native "
                                                  "provider) rather than a skill or a one-off command."},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "session_id": {"type": "string", "description": "Exact id from the digest."},
                                "quote": {"type": "string",
                                          "description": "Exact words copied from the digest, max 120 chars."},
                            },
                            "required": ["session_id", "quote"],
                        },
                    },
                    "search_terms": {"type": "array", "items": {"type": "string"},
                                     "description": "2-4 lowercase words naming the capability, for catalog matching."},
                },
                "required": ["title", "job", "why_plugin", "evidence", "search_terms"],
            },
        }
    },
    "required": ["recommendations"],
}

INSTRUCTIONS = """You analyse a log of an AI agent's real sessions to find where a PLUGIN would have \
replaced repeated manual work.

A plugin is right when the work (a) happens repeatedly, (b) needs something a skill cannot do — \
hook into the turn, persist state, register a provider/tool, run on a schedule, or render a native \
UI — and (c) is a coherent job, not "install a library".

Rules you must follow:
- Recommend nothing that the log does not show. No generic advice.
- Quote the user's own words, copied exactly from the digest, max 120 characters.
- Cite only session ids that appear in the digest. Never invent one.
- Prefer work that appears in 2+ sessions. If a single session shows a large block of repeated \
manual work, say so and cite it.
- If the real problem was a missing binary, a broken virtualenv, or a one-off research question, \
do NOT recommend a plugin for it.
- 1 to 4 recommendations, most valuable first. Return an empty list if the log does not support any.
- search_terms must be words that would appear in a plugin catalogue entry for this capability."""


# ---------- cache

def _cache_table() -> sqlite3.Connection:
    conn = _CORE._db()
    conn.execute("""CREATE TABLE IF NOT EXISTS recommendations (
        key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL,
        model TEXT, digest_stats TEXT)""")
    return conn


def cache_key(days: int, date_from: str, date_to: str, model: str = "active") -> str:
    raw = f"{PROMPT_VERSION}|{days}|{date_from}|{date_to}|{model}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def cached(days: int, date_from: str, date_to: str, max_age: int = CACHE_TTL_SECONDS) -> Optional[dict]:
    try:
        with _cache_table() as conn:
            row = conn.execute("SELECT payload, created_at FROM recommendations WHERE key = ?",
                               (cache_key(days, date_from, date_to),)).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    payload = json.loads(row[0])
    age = time.time() - float(row[1])
    if age > max_age:
        return None
    payload["cached"] = True
    payload["age_seconds"] = int(age)
    return payload


def _store(payload: dict, days: int, date_from: str, date_to: str, model: str, stats: dict) -> None:
    try:
        with _cache_table() as conn:
            conn.execute("INSERT OR REPLACE INTO recommendations (key, payload, created_at, model, digest_stats) "
                         "VALUES (?,?,?,?,?)",
                         (cache_key(days, date_from, date_to), json.dumps(payload), time.time(),
                          model, json.dumps(stats)))
    except (sqlite3.Error, TypeError):
        pass


# ---------- grounding

def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def ground(parsed: dict, digest: dict) -> tuple[list, list]:
    """Keep only recommendations whose evidence exists in the digest. Returns (kept, dropped)."""
    known = {s["id"]: s for s in digest.get("sessions", [])}
    haystack = _norm(digest.get("text", ""))
    kept, dropped = [], []
    for rec in (parsed or {}).get("recommendations", []) or []:
        if not isinstance(rec, dict):
            dropped.append({"title": str(rec)[:60], "reason": "not an object"})
            continue
        evidence, rejected = [], []
        for item in (rec.get("evidence") or [])[:4]:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("session_id") or "").strip()
            quote = " ".join(str(item.get("quote") or "").split())[:160]
            if sid not in known:
                rejected.append(f"unknown session {sid[:40]!r}")
                continue
            if len(quote) < 8 or _norm(quote) not in haystack:
                rejected.append(f"quote not in digest: {quote[:50]!r}")
                continue
            evidence.append({"session_id": sid, "quote": quote, "date": known[sid]["date"],
                             "title": known[sid]["title"]})
        title = str(rec.get("title") or "").strip()[:80]
        if not evidence:
            dropped.append({"title": title or "(untitled)", "reason": "; ".join(rejected[:2]) or "no evidence"})
            continue
        sessions = {e["session_id"] for e in evidence}
        kept.append({
            "title": title or "(untitled)",
            "job": str(rec.get("job") or "").strip()[:300],
            "why_plugin": str(rec.get("why_plugin") or "").strip()[:400],
            "evidence": evidence,
            "occurrences": len(sessions),
            "evidence_strength": "recurring" if len(sessions) >= 2 else "single-session",
            "search_terms": [str(t).strip().lower()[:30] for t in (rec.get("search_terms") or [])[:5] if str(t).strip()],
            "rejected_evidence": rejected[:2],
        })
    kept.sort(key=lambda r: (-r["occurrences"], r["title"]))
    return kept[:MAX_RECOMMENDATIONS], dropped


# ---------- catalog join

def _catalog_index() -> tuple[list, set]:
    try:
        entries = _CORE.load_catalog()["entries"]
    except Exception:
        return [], set()
    installed = set()
    try:
        installed = set(_CORE.installed_plugins() or ())
    except Exception:
        pass
    return entries, installed


def _identity_of(entry: dict) -> str:
    eid = str(entry.get("id") or entry.get("name") or "")
    return f"{eid} {entry.get('name') or eid}".lower()


def _entry_fields(entry: dict) -> tuple[str, str, str]:
    """(strong haystack, category, description) — descriptions are too loose to be evidence alone."""
    eid = str(entry.get("id") or entry.get("name") or "")
    name = str(entry.get("name") or eid)
    caps = entry.get("capabilities") or {}
    tools = " ".join(str(t) for t in (caps.get("provides_tools") or []))
    commands = " ".join(str(t) for t in (caps.get("provides_commands") or []))
    strong = f"{eid} {name} {tools} {commands}".lower()
    category = str(entry.get("category") or "").lower()
    return strong, category, str(entry.get("description") or "").lower()


def match_catalog(rec: dict, entries: list, installed: set) -> tuple[list, list]:
    """(matches, related). Strong = id/name/tools/commands/category. Related = description only."""
    terms = [t for t in rec.get("search_terms", []) if len(t) > 2]
    matches, related, seen = [], [], set()
    for entry in entries:
        eid = str(entry.get("id") or entry.get("name") or "")
        if eid in seen:
            continue
        strong, category, description = _entry_fields(entry)
        identity = _identity_of(entry)
        name_score = sum(1 for term in terms if term in identity)
        tools_score = sum(1 for term in terms if term in strong and term not in identity)
        category_hit = any(term in category for term in terms) if category else False
        weak_score = sum(1 for term in terms if term in description)
        if not (name_score or tools_score or category_hit or weak_score >= 2):
            continue
        seen.add(eid)
        row = {"id": eid, "name": str(entry.get("name") or eid), "installed": eid in installed,
               "category": category or None}
        # Only a hit on the plugin's own id/name earns an install command. A tool name or a
        # category is a lead, not proof: "publish" appearing in some plugin's tool list does not
        # make that plugin the answer to a marketplace-registry need.
        if name_score:
            row["score"] = 2 + name_score
            row["matched_on"] = "id/name"
            matches.append(row)
        elif tools_score or category_hit:
            row["score"] = tools_score + (2 if category_hit else 1)
            row["matched_on"] = "tools" if tools_score else "category"
            related.append(row)
        else:
            row["score"] = weak_score
            row["matched_on"] = "description"
            related.append(row)
    matches.sort(key=lambda h: (-h["score"], h["id"]))
    related.sort(key=lambda h: (-h["score"], h["id"]))
    return matches[:3], related[:3]


def enrich(recs: list) -> list:
    entries, installed = _catalog_index()
    for rec in recs:
        matches, related = match_catalog(rec, entries, installed)
        rec["catalog_matches"] = matches
        rec["related"] = related
        fresh = [m for m in matches if not m["installed"]]
        if fresh:
            rec["fix"] = {"kind": "install", "command": f"hermes plugins install {fresh[0]['id']}",
                          "plugin": fresh[0]["id"]}
        elif matches:
            rec["fix"] = {"kind": "installed", "command": None, "plugin": matches[0]["id"]}
        elif related:
            names = ", ".join(f"{r['id']} ({r['matched_on']})" for r in related)
            rec["fix"] = {"kind": "related", "command": None,
                          "note": f"no direct match; closest: {names}"}
        else:
            rec["fix"] = {"kind": "none",
                          "note": "no catalog plugin covers this — candidate for a contribution"}
    return recs


# ---------- run

def _extract_json(text: str) -> Optional[dict]:
    """Models wrap JSON in fences or prose. Take the outermost object that parses."""
    if not text:
        return None
    candidates = [text]
    if "```" in text:
        for chunk in text.split("```"):
            stripped = chunk.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{"):
                candidates.append(stripped)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _ask(ctx, digest_text: str, max_tokens: int) -> tuple[Optional[dict], dict]:
    """Structured lane first; fall back to a chat call when the provider rejects response_format.

    Some routes (atlas on opencode-go, for one) answer 400 "this feature is not yet supported"
    for response_format. Asking for JSON in the prompt works everywhere, so the button keeps
    working on a user's active provider instead of dying on a capability probe.
    """
    try:
        result = ctx.llm.complete_structured(
            instructions=INSTRUCTIONS,
            input=[{"type": "text", "text": digest_text}],
            json_schema=SCHEMA,
            schema_name="scout.recommendations",
            purpose="pluginscout.recommend",
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=180,
        )
        parsed = getattr(result, "parsed", None) or _extract_json(getattr(result, "text", "") or "")
        meta = {"lane": "structured", "provider": getattr(result, "provider", None),
                "model": getattr(result, "model", None),
                "tokens": getattr(getattr(result, "usage", None), "total_tokens", None),
                "cost_usd": getattr(getattr(result, "usage", None), "cost_usd", None),
                "raw": (getattr(result, "text", "") or "")[:1500]}
        return parsed, meta
    except Exception as first_exc:
        structured_error = f"{type(first_exc).__name__}: {first_exc}"
    try:
        result = ctx.llm.complete(
            messages=[
                {"role": "system", "content": f"{INSTRUCTIONS}\n\nReturn ONLY a JSON object matching "
                                              f"this schema, no prose and no code fence:\n"
                                              f"{json.dumps(SCHEMA)}"},
                {"role": "user", "content": digest_text},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=180,
            purpose="pluginscout.recommend.chat",
        )
        meta = {"lane": "chat", "provider": getattr(result, "provider", None),
                "model": getattr(result, "model", None),
                "tokens": getattr(getattr(result, "usage", None), "total_tokens", None),
                "cost_usd": getattr(getattr(result, "usage", None), "cost_usd", None),
                "structured_error": structured_error[:300],
                "raw": (getattr(result, "text", "") or "")[:1500]}
        return _extract_json(getattr(result, "text", "") or ""), meta
    except Exception as second_exc:
        raise RuntimeError(f"structured lane: {structured_error}; chat lane: "
                           f"{type(second_exc).__name__}: {second_exc}") from second_exc


def run(ctx, days: int = 7, force: bool = False, max_tokens: int = 2500) -> dict:
    """Build the digest, ask the model, ground the answer, cache it. Never raises at the caller."""
    digest = _DIGEST.build_digest(days=days)
    if not digest["sessions"]:
        return {"ok": False, "error": digest["stats"].get("error", "no sessions in window"),
                "days": days, "stats": digest["stats"]}

    if not force:
        hit = cached(days, digest["from"], digest["to"])
        if hit:
            return hit

    try:
        parsed, llm_meta = _ask(ctx, digest["text"], max_tokens)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "days": days,
                "stats": digest["stats"]}

    if not parsed:
        return {"ok": False, "error": "model returned no parseable JSON", "days": days,
                "lane": llm_meta.get("lane"), "raw": str(llm_meta.get("raw") or "")[:1500],
                "stats": digest["stats"]}

    kept, dropped = ground(parsed, digest)
    enrich(kept)
    payload = {
        "ok": True,
        "days": days,
        "from": digest["from"],
        "to": digest["to"],
        "recommendations": kept,
        "dropped": dropped,
        "stats": digest["stats"],
        "llm": llm_meta,
        "prompt_version": PROMPT_VERSION,
        "cached": False,
    }
    _store(payload, days, digest["from"], digest["to"],
           str((llm_meta or {}).get("model") or "active"), digest["stats"])
    return payload
