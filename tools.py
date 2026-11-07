"""Tool handlers. All of them return a JSON string and never raise."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Optional


def _core():
    p = Path(__file__).parent / "core.py"
    spec = importlib.util.spec_from_file_location("lazyplugin_core", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


core = _core()


def _err(exc: Exception, hint: str) -> str:
    return json.dumps({"error": str(exc), "hint": hint})


def _load_sibling(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"lazyplugin_{name}", Path(__file__).parent / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def handle_contributions(params: Optional[dict] = None, **kwargs: Any) -> str:
    """Screening needs no model; packaging writes only inside the plugin's own outbox."""
    params = params or {}
    try:
        days = max(1, min(3650, int(params.get("days") or 60)))
        limit = max(1, min(50, int(params.get("limit") or 12)))
    except (TypeError, ValueError):
        days, limit = 60, 12
    try:
        contrib = _load_sibling("skills_contrib", "skills_contrib.py")
        contrib._CORE = core
        name = str(params.get("package_name") or "").strip()
        if not name and str(params.get("mode") or "") == "submit-all":
            return json.dumps(contrib.submit_all(days=days, limit=limit))
        if name:
            mode = str(params.get("mode") or "")
            if mode == "submit":
                return json.dumps(contrib.submit(name, days=days))
            return json.dumps(contrib.package(name, days=days))
        return json.dumps(contrib.run(days=days, limit=limit))
    except Exception as exc:
        return _err(exc, "skill screening failed; nothing was written")


def handle_readiness(params: Optional[dict] = None, **kwargs: Any) -> str:
    """Facts about submittability; nothing is ranked and nothing is pushed."""
    params = params or {}
    try:
        mod = _load_sibling("readiness", "readiness.py")
        mod._CORE = core
        name = str(params.get("prepare") or "").strip()
        if name:
            return json.dumps(mod.prepare(name, deep=params.get("deep", True) is not False))
        return json.dumps(mod.audit(deep=params.get("deep", True) is not False))
    except Exception as exc:
        return _err(exc, "readiness audit failed; nothing was written")


def _creator():
    mod = _load_sibling("creator", "creator.py")
    mod._CORE = core
    return mod


def handle_create(params: Optional[dict] = None, **kwargs: Any) -> str:
    """Describe it or point at a source; the validator judges the result."""
    params = params or {}
    try:
        ctx, meta = _load_sibling("ctxbridge", "ctxbridge.py").find()
        llm = getattr(ctx, "llm", None) if ctx is not None else None
        kind = str(params.get("source_kind") or "").strip()
        source = str(params.get("source_name") or "").strip()
        idea = str(params.get("idea") or "").strip() or (f"Turn this {kind} into a plugin: {source}" if source else "")
        creator = _creator()
        context = creator.source_context(core, kind, source) if source else ""
        drafted = creator.draft_spec(idea, llm, context)
        if not drafted.get("ok"):
            drafted["ctx"] = meta
            return json.dumps(drafted)
        out = creator.create(drafted["spec"])
        out["draft"] = {"stage": drafted.get("stage"), "meta": drafted.get("meta")}
        return json.dumps(out)
    except Exception as exc:
        return _err(exc, "plugin build failed; nothing was installed")


def handle_sources(params: Optional[dict] = None, **kwargs: Any) -> str:
    try:
        skills = [{"name": s.get("name"), "description": s.get("description") or "",
                   "lines": s.get("lines") or 0}
                  for s in core.scan_skills() if s.get("agent_created")]
        jobs = []
        try:
            raw = json.loads((core.hermes_home() / "cron" / "jobs.json").read_text(encoding="utf-8"))
            raw = raw if isinstance(raw, list) else raw.get("jobs", [])
            jobs = [{"name": j.get("name") or j.get("id"),
                     "schedule": (j.get("schedule") or {}).get("expr", ""),
                     "enabled": bool(j.get("enabled"))} for j in raw]
        except Exception:
            pass
        return json.dumps({"ok": True, "skills": sorted(skills, key=lambda s: s["name"] or ""),
                           "cron": jobs})
    except Exception as exc:
        return _err(exc, "could not list sources")


def handle_built(params: Optional[dict] = None, **kwargs: Any) -> str:
    try:
        root = core.state_dir() / "created"
        rows = []
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if (child / "plugin.yaml").exists():
                    rows.append({"name": child.name, "dir": str(child)})
        return json.dumps({"ok": True, "created": rows})
    except Exception as exc:
        return _err(exc, "could not list generated plugins")


HANDLERS = {
    "lazyplugin_create": handle_create,
    "lazyplugin_sources": handle_sources,
    "lazyplugin_built": handle_built,
}
