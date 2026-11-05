"""Dashboard backend for the Scout tab. Routes mount at /api/plugins/pluginscout/.

Handlers are async and push blocking work to a thread: the dashboard's event loop also serves
chat and Desktop, so a synchronous catalog scan here would stall unrelated requests.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_CORE_PATH = _PLUGIN_DIR / "core.py"


def _core():
    spec = importlib.util.spec_from_file_location("pluginscout_core_api", _CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _recommend_mod():
    spec = importlib.util.spec_from_file_location(
        "pluginscout_recommend_api", _PLUGIN_DIR / "recommend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod._CORE = _core()
    return mod


def _find_ctx():
    """The plugin's ctx, published by __init__.register() in this same host process."""
    spec = importlib.util.spec_from_file_location(
        "pluginscout_ctxbridge_api", _PLUGIN_DIR / "ctxbridge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.find_ctx()


router = APIRouter()


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


@router.get("/health")
async def health(probe: int = 0):
    ctx, meta = _find_ctx()
    out = {"ctx": meta, "plugin_dir": str(_PLUGIN_DIR)}
    if ctx is not None and probe:
        try:
            result = await asyncio.to_thread(lambda: ctx.llm.complete(
                messages=[{"role": "user", "content": "Reply with the single word: pong"}],
                max_tokens=8, temperature=0.0, purpose="pluginscout.health"))
            out["llm"] = {"ok": True, "text": (result.text or "").strip(),
                          "provider": result.provider, "model": result.model,
                          "tokens": getattr(result.usage, "total_tokens", None)}
        except Exception as exc:
            out["llm"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


@router.get("/recommend")
async def recommend_cached(days: int = 7):
    """Cheap read: the cached analysis, or an explicit "nothing cached yet"."""
    rec = _recommend_mod()
    digest = await asyncio.to_thread(rec._DIGEST.build_digest, max(1, min(365, days)))
    if not digest["sessions"]:
        return {"ok": False, "cached": False, "days": days,
                "error": digest["stats"].get("error", "no sessions in window")}
    hit = rec.cached(digest["days"], digest["from"], digest["to"])
    if hit:
        return hit
    return {"ok": False, "cached": False, "days": days, "from": digest["from"], "to": digest["to"],
            "reason": "no cached analysis for this window",
            "stats": digest["stats"], "llm_available": _find_ctx()[0] is not None}


@router.post("/recommend")
async def recommend_run(payload: dict | None = None):
    """The button. Spends one model call unless a fresh cached analysis exists for the window."""
    payload = payload or {}
    try:
        days = max(1, min(365, int(payload.get("days") or 7)))
    except (TypeError, ValueError):
        days = 7
    force = bool(payload.get("force"))
    ctx, meta = _find_ctx()
    if ctx is None:
        return {"ok": False, "cached": False, "days": days, "needs_llm": True, "ctx": meta,
                "error": "this host cannot reach the model from the dashboard process; "
                         "ask the agent to run pluginscout_recommend instead",
                "fallback": "pluginscout_recommend"}
    rec = _recommend_mod()
    return await asyncio.to_thread(rec.run, ctx, days, force)
