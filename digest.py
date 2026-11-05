"""Digest of recent sessions for the LLM pass: intent + tools + failures, capped and ordered.

The digest is the whole input contract for `recommend.py`. Kept deliberately small (default 60k
chars ≈ 18k tokens) so a button press costs cents, not dollars.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

MAX_ASKS = 6
ASK_CHARS = 150
MAX_FAILURES = 4


def state_db_path() -> Path:
    return _CORE.hermes_home() / "state.db"


def connect() -> Optional[sqlite3.Connection]:
    path = state_db_path()
    if not path.is_file():
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None


def _when(value) -> Optional[datetime.datetime]:
    """state.db stores epoch floats; older rows may carry strings."""
    if value is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(value))
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromisoformat(str(value)[:19])
        except ValueError:
            return None


def _flatten(content) -> str:
    """Message content is a str, or a list of blocks. Return plain text."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return content if isinstance(content, str) else ""


def _one_line(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


_ERR = re.compile(r"(\w+ ?(?:not found|not recognized)|no such file|permission denied)", re.I)


def _failure(text: str) -> Optional[str]:
    """Only real failures: a JSON payload with a non-empty error, or a shell not-found."""
    stripped = (text or "").strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        err = obj.get("error")
        if err in (None, "", False, "null") and obj.get("success") is not False:
            return None
        return _one_line(str(err) if err not in (None, "") else stripped, 110)
    match = _ERR.search(stripped)
    return _one_line(match.group(0), 60) if match else None


def build_digest(days: int = 7, max_sessions: int = 40, char_budget: int = 60_000,
                 now: Optional[datetime.datetime] = None) -> dict:
    """Sessions in the window, richest-intent first, flattened to a prompt-ready string."""
    days = max(1, min(365, int(days)))
    end = now or datetime.datetime.now()
    start = end - datetime.timedelta(days=days)
    empty = {"from": start.date().isoformat(), "to": end.date().isoformat(), "days": days,
             "sessions": [], "text": "", "stats": {"sessions": 0, "asks": 0, "tool_calls": 0}}

    conn = connect()
    if conn is None:
        empty["stats"]["error"] = f"no state.db at {state_db_path()}"
        return empty
    try:
        rows = conn.execute(
            """SELECT id, COALESCE(title,''), COALESCE(started_at, 0)
               FROM sessions WHERE started_at IS NOT NULL AND started_at >= ?
               ORDER BY started_at DESC LIMIT ?""",
            (start.timestamp(), max_sessions * 3)).fetchall()
        sessions = []
        for sid, title, started in rows:
            asks = conn.execute(
                """SELECT substr(content, 1, 400) FROM messages
                   WHERE session_id = ? AND role = 'user' ORDER BY timestamp LIMIT ?""",
                (sid, MAX_ASKS)).fetchall()
            asks = [a for a in (_one_line(_flatten(t), ASK_CHARS) for (t,) in asks) if a]
            if not asks:
                continue
            tools = conn.execute(
                """SELECT COALESCE(tool_name,'?') AS t, COUNT(*) FROM messages
                   WHERE session_id = ? AND role = 'tool' GROUP BY t
                   ORDER BY COUNT(*) DESC LIMIT 6""", (sid,)).fetchall()
            failures = []
            for (content,) in conn.execute(
                    """SELECT substr(content, 1, 800) FROM messages
                       WHERE session_id = ? AND role = 'tool' ORDER BY timestamp DESC LIMIT 25""",
                    (sid,)).fetchall():
                hit = _failure(_flatten(content))
                if hit and hit not in failures:
                    failures.append(hit)
                if len(failures) >= MAX_FAILURES:
                    break
            sessions.append({
                "id": sid, "title": _one_line(title, 80),
                "date": (_when(started) or end).date().isoformat(),
                "asks": asks,
                "tools": {name: count for name, count in tools},
                "failures": failures,
                "tool_calls": sum(count for _n, count in tools),
            })
            if len(sessions) >= max_sessions:
                break
    finally:
        conn.close()

    if not sessions:
        empty["stats"]["error"] = f"no sessions with user messages since {start.date().isoformat()}"
        return empty

    lines = [f"WINDOW {start.date().isoformat()} to {end.date().isoformat()} ({days} days)",
             f"SESSIONS {len(sessions)}", ""]
    used = sum(len(x) for x in lines)
    kept = []
    for sess in sessions:
        block = [f"## {sess['id']} | {sess['date']} | \"{sess['title']}\" | {sess['tool_calls']} tool calls"]
        block.append("asks:")
        block += [f"  - {a}" for a in sess["asks"]]
        if sess["tools"]:
            block.append("tools: " + ", ".join(f"{n}x{c}" for n, c in sess["tools"].items()))
        if sess["failures"]:
            block.append("failures: " + "; ".join(sess["failures"]))
        chunk = "\n".join(block) + "\n"
        if used + len(chunk) > char_budget:
            break
        lines.append(chunk)
        used += len(chunk)
        kept.append(sess)

    return {
        "from": start.date().isoformat(), "to": end.date().isoformat(), "days": days,
        "sessions": kept, "text": "\n".join(lines),
        "stats": {"sessions": len(kept), "asks": sum(len(s["asks"]) for s in kept),
                  "tool_calls": sum(s["tool_calls"] for s in kept), "chars": used,
                  "truncated": len(kept) < len(sessions)},
    }
