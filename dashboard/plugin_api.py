"""Dashboard backend for the Scout tab. Routes mount at /api/plugins/pluginscout/.

Handlers are async and push blocking work to a thread: the dashboard's event loop also serves
chat and Desktop, so a synchronous catalog scan here would stall unrelated requests.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_CORE_PATH = _PLUGIN_DIR / "core.py"

router = APIRouter()


def _core():
    spec = importlib.util.spec_from_file_location("pluginscout_core_api", _CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _readiness_mod():
    spec = importlib.util.spec_from_file_location(
        "pluginscout_readiness_api", _PLUGIN_DIR / "readiness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _contrib_mod():
    spec = importlib.util.spec_from_file_location(
        "pluginscout_contrib_api", _PLUGIN_DIR / "skills_contrib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod._CORE = _core()
    return mod


@router.get("/report")
async def report(format: str = "json", min_match: int = 1):
    core = _core()
    data = await asyncio.to_thread(core.build_report, "full", max(1, min(10, min_match)))
    if format == "summary":
        data["text"] = core.summary_text(data)
    return data


@router.post("/refresh")
async def refresh():
    core = _core()
    payload = await asyncio.to_thread(core.load_catalog, True)
    index, _ = core.gate_index(payload["entries"])
    return {"entries": len(payload["entries"]), "identifiers": len(index),
            "generated_at": payload.get("generated_at"), "source": payload.get("source")}


@router.get("/gaps")
async def gaps(limit: int = 20):
    core = _core()
    return await asyncio.to_thread(core.gaps, max(1, min(200, limit)))


@router.get("/contributions")
async def contributions(days: int = 60, limit: int = 12):
    """Screen agent-written skills: publishable, needs scrubbing, or keep private."""
    mod = _contrib_mod()
    return await asyncio.to_thread(mod.run, max(1, min(3650, days)), max(1, min(50, limit)))


@router.post("/contributions/package")
async def contributions_package(payload: dict | None = None):
    """Stage a submission bundle in the plugin's outbox. Refuses anything it called private."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name is required"}, status_code=400)
    try:
        days = max(1, min(3650, int(payload.get("days") or 60)))
    except (TypeError, ValueError):
        days = 60
    mod = _contrib_mod()
    return await asyncio.to_thread(mod.package, name, days)


@router.post("/contributions/submit")
async def contributions_submit(payload: dict | None = None):
    """Stage the portable package + catalog entry + PR steps. Nothing is pushed."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name is required"}, status_code=400)
    try:
        days = max(1, min(3650, int(payload.get("days") or 60)))
    except (TypeError, ValueError):
        days = 60
    mod = _contrib_mod()
    return await asyncio.to_thread(mod.submit, name, days)


@router.post("/contributions/submit-all")
async def contributions_submit_all(payload: dict | None = None):
    """Prepare and validate every publishable candidate in one pass."""
    payload = payload or {}
    try:
        days = max(1, min(3650, int(payload.get("days") or 60)))
    except (TypeError, ValueError):
        days = 60
    mod = _contrib_mod()
    return await asyncio.to_thread(mod.submit_all, days)


@router.get("/sources")
async def sources():
    """What the creator can build from: the agent's own skills and the scheduled jobs."""
    return await asyncio.to_thread(_sources)


def _sources() -> dict:
    core = _core()
    outbox = core.state_dir() / "created"
    skills = []
    try:
        for skill in core.scan_skills():
            if not skill.get("agent_created"):
                continue
            skills.append({"name": skill.get("name"), "description": skill.get("description") or "",
                           "lines": skill.get("lines") or 0, "path": skill.get("path")})
    except Exception as exc:
        skills = [{"name": "unavailable", "description": f"{type(exc).__name__}", "lines": 0}]
    jobs = []
    try:
        raw = json.loads((core.hermes_home() / "cron" / "jobs.json").read_text(encoding="utf-8"))
        raw = raw if isinstance(raw, list) else raw.get("jobs", [])
        for job in raw:
            schedule = job.get("schedule") or {}
            jobs.append({
                "id": job.get("id"),
                "name": job.get("name") or job.get("id"),
                "schedule": schedule.get("expr") or schedule.get("value") or "",
                "enabled": bool(job.get("enabled")),
                "prompt": (job.get("prompt") or "")[:400],
                "failures": job.get("failure_streak") or 0,
            })
    except Exception as exc:
        jobs = [{"id": "unavailable", "name": f"{type(exc).__name__}", "schedule": "", "enabled": False}]
    created = []
    if outbox.is_dir():
        created = sorted(p.name for p in outbox.iterdir() if (p / "plugin.yaml").exists())
    return {"ok": True, "skills": sorted(skills, key=lambda s: s["name"] or ""),
            "cron": jobs, "already_generated": created, "outbox": str(outbox)}


@router.get("/readiness")
async def readiness(deep: int = 1):
    """Every installed plugin against the catalog admission rules. Facts, no ranking."""
    mod = _readiness_mod()
    return await asyncio.to_thread(mod.audit, bool(deep))


@router.post("/readiness/prepare")
async def readiness_prepare(payload: dict | None = None):
    """Generate the catalog entry for one plugin. Never pushes anything."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name is required"}, status_code=400)
    mod = _readiness_mod()
    return await asyncio.to_thread(mod.prepare, name)


@router.get("/health")
async def health():
    """Is the backend the one on disk? Route existence is the cheap signal; the payload is the proof."""
    core = _core()
    report = await asyncio.to_thread(core.build_report)
    return {
        "ok": True,
        "routes": ["report", "refresh", "gaps", "contributions", "contributions/package",
                   "contributions/submit", "health"],
        "catalog_entries": report["catalog"]["entries"],
        "skills": report["headline"]["total_skills"],
        "outbox": str(core.state_dir() / "outbox"),
    }
