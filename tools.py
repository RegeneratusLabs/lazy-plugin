"""Tool handlers. All of them return a JSON string and never raise."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Optional


def _core():
    p = Path(__file__).parent / "core.py"
    spec = importlib.util.spec_from_file_location("pluginscout_core", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


core = _core()


def _err(exc: Exception, hint: str) -> str:
    return json.dumps({"error": str(exc), "hint": hint})


def handle_report(params: Optional[dict] = None, **kwargs: Any) -> str:
    params = params or {}
    fmt = str(params.get("format") or "summary").lower()
    if fmt not in ("summary", "full", "json"):
        fmt = "summary"
    try:
        min_match = max(1, min(10, int(params.get("min_match") or 1)))
    except (TypeError, ValueError):
        min_match = 1
    try:
        report = core.build_report(fmt, min_match)
        if fmt == "summary":
            report["text"] = core.summary_text(report)
        return json.dumps(report)
    except Exception as exc:
        return _err(exc, "catalog or skills directory unreadable; run pluginscout_refresh and retry")


def handle_refresh(params: Optional[dict] = None, **kwargs: Any) -> str:
    try:
        payload = core.load_catalog(force=True)
        index, _ = core.gate_index(payload["entries"])
        return json.dumps({"entries": len(payload["entries"]),
                           "identifiers": len(index),
                           "generated_at": payload.get("generated_at"),
                           "source": payload.get("source")})
    except Exception as exc:
        return _err(exc, "network unavailable; the cached catalog is still usable offline")


def handle_explain(params: Optional[dict] = None, **kwargs: Any) -> str:
    target = str((params or {}).get("target") or "").strip()
    if not target:
        return json.dumps({"error": "target required",
                           "hint": "pass a skill name from pluginscout_report or a gap signature"})
    try:
        report = core.build_report("full")
        for m in report["matches"]:
            if m["skill"].lower() == target.lower():
                entry = (core.gate_index(core.load_catalog()["entries"])[1] or {}).get(m["plugin"]) or {}
                return json.dumps({
                    "kind": "skill_match",
                    "skill": m["skill"],
                    "plugin": m["plugin"],
                    "evidence": m["ids"],
                    "plugin_description": entry.get("description"),
                    "needs_env": m.get("needs_env") or [],
                    "install": m["install"],
                    "rule": "an identifier the skill actually invokes equals this plugin's name, "
                            "a tool it provides, or its repo name",
                })
        for g in report["gaps"].get("top", []):
            if g["signature"].lower() == target.lower():
                return json.dumps({"kind": "gap", **g,
                                   "rule": "recorded from a real tool result, not inferred"})
        return json.dumps({"error": f"no match or gap named {target!r}",
                           "hint": "call pluginscout_report with format='full' to list what exists"})
    except Exception as exc:
        return _err(exc, "report failed; check the skills directory and catalog cache")


HANDLERS = {
    "pluginscout_report": handle_report,
    "pluginscout_refresh": handle_refresh,
    "pluginscout_explain": handle_explain,
}
