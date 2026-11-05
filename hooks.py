"""Runtime half: turn real tool failures into measured capability gaps.

Every hook body is wrapped: a diagnostic plugin must never break a turn.
"""

from __future__ import annotations

import importlib.util
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _core():
    p = Path(__file__).parent / "core.py"
    spec = importlib.util.spec_from_file_location("lazyplugin_core", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


core = _core()

_NOT_FOUND = re.compile(
    r"(command not found|no such file or directory|ModuleNotFoundError|"
    r"is not recognized as|not found: |unknown command)", re.I)
_HEAD = re.compile(r"[A-Za-z0-9_.+-]{2,}")

_pending: list[dict] = []
_shellouts: dict[str, Counter] = defaultdict(Counter)
FLUSH_AT = 20


def _text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        try:
            return str(result.get("error") or result.get("output") or "") or repr(result)[:400]
        except Exception:
            return ""
    return ""


def _session(kw: dict) -> str:
    for key in ("session_id", "session", "conversation_id", "thread_id"):
        v = kw.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _queue(kind: str, signature: str, *, tool: str = "", snippet: str = "", session: str = "") -> None:
    if not signature:
        return
    _pending.append({"kind": kind, "signature": signature, "tool": tool,
                     "snippet": snippet, "session_id": session})
    if len(_pending) >= FLUSH_AT:
        flush()


def flush() -> int:
    """Write buffered gaps. Returns how many rows were attempted."""
    if not _pending:
        return 0
    batch, _pending[:] = list(_pending), []
    ok = 0
    for ev in batch:
        try:
            if core.record_gap(ev["kind"], ev["signature"], tool=ev["tool"],
                               snippet=ev["snippet"], session_id=ev["session_id"]):
                ok += 1
        except Exception:
            logger.debug("lazy-plugin: gap write failed", exc_info=True)
    try:
        core.prune_gaps()
    except Exception:
        pass
    return ok


def on_post_tool_call(tool_name: Optional[str] = None, args: Any = None, result: Any = None,
                      **kwargs: Any) -> None:
    try:
        session = _session(kwargs)
        text = _text(result)
        argv = args if isinstance(args, dict) else {}
        command = str(argv.get("command") or argv.get("cmd") or "")

        if text and _NOT_FOUND.search(text):
            m = re.search(r"'([^']+)'|`([^`]+)`|\"([^\"]+)\"", text)
            token = next((g for g in (m.groups() if m else ()) if g), "")
            if not token and command:
                token = (command.split() or [""])[0]
            token = (_HEAD.search(token.strip()) or [""])[0] if token else ""
            _queue("cmd_not_found", f"cmd:{token or 'unknown'}", tool=tool_name or "",
                   snippet=text.strip()[:120], session=session)
            return

        if text and (text.lstrip().startswith('{"error"') or '"success": false' in text
                     or text.lstrip().startswith("Error:")):
            _queue("tool_error", f"tool:{tool_name or 'unknown'}", tool=tool_name or "",
                   snippet=text.strip()[:120], session=session)
            return

        if command and session:
            head = " ".join(command.split()[:3])
            _shellouts[session][head] += 1
            if _shellouts[session][head] == 3:
                _queue("repeated_shellout", f"shellout:{head}", tool=tool_name or "",
                       snippet=command[:120], session=session)
    except Exception:
        logger.debug("lazy-plugin: post_tool_call failed", exc_info=True)


def on_skill_lifecycle(action: Optional[str] = None, skill_name: Optional[str] = None,
                       **kwargs: Any) -> None:
    try:
        if (action or "").lower() != "created" or not skill_name:
            return
        _queue("skill_created", f"skill:{skill_name}", tool="skill_manage",
               snippet=f"agent wrote skill {skill_name}", session=_session(kwargs))
    except Exception:
        logger.debug("lazy-plugin: on_skill_lifecycle failed", exc_info=True)


def on_session_end(**kwargs: Any) -> None:
    try:
        flush()
        _shellouts.clear()
    except Exception:
        logger.debug("lazy-plugin: on_session_end failed", exc_info=True)
