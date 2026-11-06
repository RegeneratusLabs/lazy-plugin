"""Requests a page hands to the agent.

A dashboard page cannot start a turn: the chat channel is a websocket the TUI owns, and
`window.hermes.send` only exists inside `::preview` widgets. So a description typed into the page is
written down here, and the agent picks it up and calls `lazyplugin_create` itself — inside a turn,
where provider credentials are scoped.

When a profile can resolve its provider key out of turn, the page skips this and builds directly.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

RETENTION_HOURS = 24


def _queue_dir(hermes_home: Path) -> Path:
    path = Path(hermes_home) / "lazy-plugin" / "requests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def enqueue(hermes_home: Path, idea: str, source_kind: str = "", source_name: str = "") -> dict:
    request = {
        "id": uuid.uuid4().hex[:10],
        "idea": (idea or "").strip(),
        "source_kind": source_kind,
        "source_name": source_name,
        "created": time.time(),
    }
    path = _queue_dir(hermes_home) / f"{request['id']}.json"
    path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return request


def pending(hermes_home: Path) -> list[dict]:
    """Old requests are dropped rather than replayed: a stale idea built later is a surprise."""
    cutoff = time.time() - RETENTION_HOURS * 3600
    rows = []
    for path in sorted(_queue_dir(hermes_home).glob("*.json")):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if request.get("created", 0) < cutoff:
            path.unlink(missing_ok=True)
            continue
        rows.append(request)
    return rows


def finish(hermes_home: Path, request_id: str) -> bool:
    path = _queue_dir(hermes_home) / f"{request_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def as_prompt(requests: list[dict]) -> str:
    """What the agent reads: the request, the tool, and the rule about not inventing."""
    if not requests:
        return ""
    lines = ["Plugin build requests from the Lazy Plugin page:"]
    for request in requests:
        source = (f" (from {request['source_kind']} \"{request['source_name']}\")"
                  if request.get("source_name") else "")
        lines.append(f"- [{request['id']}] {request['idea']}{source}")
    lines.append("")
    lines.append("For each: call lazyplugin_create with the idea. If the request has no URL, path or "
                 "command to act on, ask the user one question instead of building an empty tool. "
                 "Then say what the validator reported.")
    return "\n".join(lines)
