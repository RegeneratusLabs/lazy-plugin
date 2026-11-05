"""Backfill: mine past session transcripts for capability gaps.

A skill cannot do this. It would have to read every transcript into context; there are 128 files
and 32 MB of them. The plugin walks them on disk, keeps only the measured events, and persists them.

Classifier is deliberately narrow. Most "errors" in a transcript are the model's own malformed
calls (`patch` old_string mismatch, missing params, memory budget) — those are not capability gaps
and reporting them would be noise. Only a tool the agent reached for and the machine did not have
counts.
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple


def _core():
    p = Path(__file__).parent / "core.py"
    spec = importlib.util.spec_from_file_location("pluginscout_core_hist", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


CORE = _core()

#: Ordered: first match wins. Each yields (kind, identifier) or None.
PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("pkg_missing", re.compile(r"No module named '?([A-Za-z0-9_][A-Za-z0-9_.]*)")),
    ("pkg_missing", re.compile(r"ModuleNotFoundError:\s*(?:No module named )?'?([A-Za-z0-9_][A-Za-z0-9_.]*)")),
    ("cmd_missing", re.compile(r"(?:bash|sh|zsh|dash):\s*(?:line \d+:\s*)?([^\s:]+):\s*command not found", re.I)),
    ("cmd_missing", re.compile(r"Command '([^']+)' not found", re.I)),
    ("cmd_missing", re.compile(r"exec: \"?([^\s\"]+)\"?: executable file not found", re.I)),
    ("cmd_missing", re.compile(r"'([^']+)' is not recognized as an internal or external command", re.I)),
    ("cmd_missing", re.compile(r"([A-Za-z0-9_.+-]+):\s*not found\b")),
)

#: Noise that must never become a gap: the model's own bad calls, HTTP 404s from its own servers.
NOISE = re.compile(
    r"(old_string|path required|question text is required|memory at \d|"
    r"requires either prompt|invalid argument|must be|missing required|"
    r"detail\\?\"?:\\?\"?not found|404 not found|File not found:|Path not found:|"
    r"Task not found|Skill '[^']*' not found|Job with ID)", re.I)

#: Modules that are never a missing capability: the agent's own code, or generic package names a
#: malformed import produced. A real gap names a third-party package.
NOT_A_DEPENDENCY = {
    "tools", "tool", "core", "config", "configs", "utils", "util", "main", "app", "apps", "agent",
    "agents", "cli", "server", "router", "routers", "tests", "test", "src", "lib", "libs",
    "scripts", "script", "models", "model", "schemas", "schema", "plugins", "plugin", "skills",
    "skill", "memory", "prompts", "prompt", "hermes", "hermes_core", "hermes_agent", "gateway",
    "hooks", "handlers", "api", "web", "dashboard", "cron", "session", "sessions", "voice", "tts",
    "stt", "asr", "llm", "chat", "ui", "db", "database", "helpers", "common", "shared", "build",
    "dist", "setup", "conftest", "typing", "types", "abc", "os", "sys", "json", "re", "time",
    "datetime", "pathlib", "subprocess", "logging", "asyncio", "tempfile", "shutil", "argparse",
    "collections", "itertools", "functools", "math", "random", "hashlib", "base64", "csv", "io",
    "uuid", "threading", "sqlite3", "urllib", "http", "socket", "ssl", "email", "html", "xml",
}

_TS = re.compile(r'"timestamp":\s*"([0-9T:\-\.\+Z]+)"')


def classify(text: str) -> Optional[Tuple[str, str]]:
    """``(kind, signature)`` for a real missing-capability event, else None."""
    if not text or NOISE.search(text):
        return None
    for kind, pattern in PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        token = (m.group(1) or "").strip().strip("\"'`")
        if not token:
            continue
        if kind == "pkg_missing":
            token = token.split(".")[0]
            if token.strip().lower() in NOT_A_DEPENDENCY:
                return None
        else:
            token = token.rsplit("/", 1)[-1]
        token = token.strip().lower()
        if len(token) < 3:
            continue
        prefix = "pkg" if kind == "pkg_missing" else "cmd"
        return ("cmd_not_found", f"{prefix}:{token}")
    return None


def _content(rec: dict) -> str:
    raw = rec.get("content")
    if isinstance(raw, str):
        text = raw
    else:
        text = json.dumps(raw or "")
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except Exception:
            return text
        if isinstance(obj, dict):
            return " ".join(str(obj.get(k) or "") for k in ("output", "error", "message", "detail"))
    return text


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
    for path in iter_files(max_sessions):
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
                hit = classify(_content(rec))
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
                                    snippet=_content(rec).strip()[:120], session_id=session_id,
                                    source="backfill")
                    events += 1
                except Exception:
                    continue
    return {"sessions": len(iter_files(max_sessions)), "tool_records": scanned,
            "events_recorded": events, "skipped_outside_window": skipped_old,
            "days": days}
