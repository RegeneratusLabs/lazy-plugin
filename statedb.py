"""state.db source: one indexed table, ~80k tool messages, real epoch timestamps.

Why this exists: the JSONL path sees one file per session (99 files, ~4,900 tool results).
`state.db` has every tool result the profile ever wrote, timestamped, so the same classifier
produces a time series instead of a recent sample. The heatmap is only possible from here.

Read-only. Never writes, never migrates, and degrades to the JSONL path if the schema moves.
"""

from __future__ import annotations

import datetime
import importlib.util
import sqlite3
from pathlib import Path
from typing import Optional


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", Path(__file__).parent / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def db_path() -> Path:
    return _load("core", "core.py").hermes_home() / "state.db"


def available() -> bool:
    p = db_path()
    if not p.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as conn:
            conn.execute("SELECT 1 FROM messages LIMIT 1")
        return True
    except Exception:
        return False


def _ts(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mine(days: int = 3650, limit: int = 400_000) -> dict:
    """Classify every tool message in state.db and record the real gaps with their real time."""
    core = _load("core", "core.py")
    classify = _load("classify", "classify.py")
    if not available():
        return {"source": "state.db", "available": False, "events_recorded": 0,
                "hint": "no readable state.db; use the JSONL backfill instead"}

    cutoff = datetime.datetime.now().timestamp() - max(1, days) * 86400
    scanned = recorded = skipped_old = 0
    replaced = core.clear_mined()
    try:
        conn = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    except Exception as exc:
        return {"source": "state.db", "available": False, "events_recorded": 0, "error": str(exc)}

    with conn:
        try:
            total_tool = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'tool'").fetchone()[0]
        except Exception:
            total_tool = 0
        # Cheap SQL prefilter + truncation: full content is often a 50 KB browser snapshot.
        # Without this the classifier regexes 80k large strings (~53s); with it, ~2.7k (~2s).
        rows = conn.execute(
            """SELECT session_id, tool_name, substr(content, 1, 8000), timestamp
               FROM messages
               WHERE role = 'tool' AND (
                     content LIKE '%command not found%'
                  OR content LIKE '%No module named%'
                  OR content LIKE '%ModuleNotFoundError%'
                  OR content LIKE '%is not recognized as%'
                  OR content LIKE '%executable file not found%')
               ORDER BY timestamp DESC LIMIT ?""", (limit,)).fetchall()

    batch = []
    for session_id, tool_name, content, ts in rows:
        scanned += 1
        text = classify.content_of({"content": content})
        hit = classify.classify(text)
        if not hit:
            continue
        when = _ts(ts)
        if when and when < cutoff:
            skipped_old += 1
            continue
        kind, signature = hit
        batch.append((kind, signature, str(tool_name or ""), text.strip()[:120],
                      str(session_id or ""), when, "statedb"))
    try:
        recorded = core.record_gaps_bulk(batch)
    except Exception:
        recorded = 0
    conn.close()
    return {"source": "state.db", "available": True, "tool_messages": total_tool,
            "candidates": scanned, "events_recorded": recorded,
            "skipped_outside_window": skipped_old, "days": days, "replaced": replaced}
