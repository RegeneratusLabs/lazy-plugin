"""JSONL source: one file per session. Kept as the fallback.

Superseded as the primary source by `statedb.py` — same classifier, ~16x the records, real epoch
timestamps (the JSONL path has no timestamps at all on some records). This path survives a
state.db schema change and works on a machine whose db is locked.
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Optional

_TS = re.compile(r'"timestamp":\s*"([0-9T:\-\.\+Z]+)"')


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", Path(__file__).parent / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_cls = _load("classify", "classify.py")
CORE = _load("core", "core.py")

#: One classifier for every source — re-exported so tests and callers never fork the noise filter.
classify = _cls.classify
_content = _cls.content_of
NOISE = _cls.NOISE
NOT_A_DEPENDENCY = _cls.NOT_A_DEPENDENCY


def iter_files(limit: Optional[int] = None) -> list:
    root = CORE.hermes_home() / "sessions"
    try:
        files = sorted((p for p in root.glob("*.jsonl") if p.is_file()), reverse=True)
    except OSError:
        return []
    return files[:limit] if limit else files


def backfill(days: int = 90, max_sessions: Optional[int] = 200) -> dict:
    """Record gaps from past transcripts. Idempotent: re-running only bumps `seen`."""
    cutoff = time.time() - max(1, days) * 86400
    scanned = events = skipped_old = 0
    replaced = CORE.clear_mined()
    files = iter_files(max_sessions)
    for path in files:
        session_id = path.stem
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"tool"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("role") != "tool":
                    continue
                scanned += 1
                text = _content(rec)
                hit = classify(text)
                if not hit:
                    continue
                ts = None
                m = _TS.search(line)
                if m:
                    try:
                        ts = time.mktime(time.strptime(m.group(1)[:19], "%Y-%m-%dT%H:%M:%S"))
                    except Exception:
                        ts = None
                if ts and ts < cutoff:
                    skipped_old += 1
                    continue
                kind, signature = hit
                try:
                    CORE.record_gap(kind, signature, tool=str(rec.get("name") or ""),
                                    snippet=text.strip()[:120], session_id=session_id,
                                    source="backfill", ts=ts)
                    events += 1
                except Exception:
                    continue
    return {"source": "jsonl", "sessions": len(files), "tool_records": scanned,
            "events_recorded": events, "skipped_outside_window": skipped_old, "days": days}
