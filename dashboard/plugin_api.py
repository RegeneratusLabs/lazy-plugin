"""Dashboard backend for the Lazy Plugin tab. Routes mount at /api/plugins/lazy-plugin/.

Handlers are async and push blocking work to a thread: the dashboard's event loop also serves
chat and Desktop, so a synchronous catalog scan here would stall unrelated requests.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
import uuid
import importlib.util
import json
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_CORE_PATH = _PLUGIN_DIR / "core.py"

router = APIRouter()


def _core():
    spec = importlib.util.spec_from_file_location("lazyplugin_core_api", _CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _readiness_mod():
    spec = importlib.util.spec_from_file_location(
        "lazyplugin_readiness_api", _PLUGIN_DIR / "readiness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _contrib_mod():
    spec = importlib.util.spec_from_file_location(
        "lazyplugin_contrib_api", _PLUGIN_DIR / "skills_contrib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod._CORE = _core()
    return mod


@router.post("/refresh")
async def refresh():
    core = _core()
    payload = await asyncio.to_thread(core.load_catalog, True)
    return {"entries": len(payload["entries"]),
            "generated_at": payload.get("generated_at"), "source": payload.get("source")}


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


def _find_ctx():
    try:
        spec = importlib.util.spec_from_file_location(
            "lazyplugin_ctxbridge", _PLUGIN_DIR / "ctxbridge.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.find()
    except Exception as exc:
        return None, {"found": False, "error": f"{type(exc).__name__}: {exc}"}


def _creator_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_creator_api", _PLUGIN_DIR / "creator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _source_context(kind: str, name: str) -> str:
    """Delegates to creator.source_context so the tool and the page cannot drift apart."""
    try:
        return _creator_mod().source_context(_core(), kind, name)
    except Exception:
        return ""


def _smoke_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_smoke_api", _PLUGIN_DIR / "smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@router.post("/created/smoke")
async def smoke_created(payload: dict | None = None):
    """Call every tool in a generated plugin for real and report what came back.

    This route is the user's own click on the page's try-it button — the only path that dispatches.
    A build (`lazyplugin_create`) runs with live off, and `smoke.py` refuses to carry a declared
    credential anywhere but a public https host the handler names.
    """
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    bundle = _bundle(name)
    if bundle is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    live = payload.get("live", True) is not False

    def run() -> dict:
        module = _smoke_mod()
        report = module.smoke(bundle, live=live)
        module.write_report(bundle, report)
        return report

    try:
        report = await asyncio.to_thread(run)
    except Exception as exc:
        # The button must always answer with a sentence, never a bare 500: a smoke test that
        # cannot run is itself a verdict the tile has to show.
        return {"ok": False, "name": name,
                "error": f"the smoke test crashed: {type(exc).__name__}: {exc}"[:400]}

    headline = _smoke_mod().headline(report)
    failing = next(
        (f"{tool.get('tool')}: {tool.get('detail')}" for tool in report.get("tools") or []
         if tool.get("status") in ("broken", "scaffold")), "")
    return {"ok": True, "smoke": report, "headline": headline,
            "verdict": report.get("verdict"), "first_failure": failing}


@router.get("/created")
async def created():
    """Everything this plugin has generated so far. Never installed, always inspectable."""
    return await asyncio.to_thread(_created)


def _created() -> dict:
    """One row per generated plugin, with everything a tile needs — no second request."""
    core = _core()
    root = core.state_dir() / "created"
    creator = _creator_mod()
    cache = _validation_cache(core)
    rows = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not (child / "plugin.yaml").exists():
                continue
            name = child.name
            try:
                manifest = creator.read_manifest(child)
            except Exception:
                manifest = {}
            modified = max((f.stat().st_mtime for f in child.rglob("*") if f.is_file()), default=0)
            check = cache.get(name)
            if not check or check.get("mtime") != modified:
                try:
                    result = creator.validate_plugin(child) or {}
                    check = {"mtime": modified, "ok": bool(result.get("ok")),
                             "tail": [line for line in (result.get("tail") or []) if line.strip()][-3:]}
                except Exception as exc:
                    # the tile still renders; install and publish re-validate anyway
                    check = {"mtime": modified, "ok": None, "tail": [f"check unavailable: {type(exc).__name__}"]}
                cache[name] = check
            published = None
            entry_path = child / "plugin-catalog" / f"{name}.yaml"
            if entry_path.exists():
                text = entry_path.read_text(encoding="utf-8", errors="replace")
                repo = re.search(r"^repo:\s*(\S+)", text, re.M)
                sha = re.search(r"^sha:\s*(\S+)", text, re.M)
                if repo:
                    published = {"repo": repo.group(1), "sha": sha.group(1) if sha else ""}
            smoke = None
            smoke_path = child / "smoke.json"
            if smoke_path.exists():
                try:
                    stored = json.loads(smoke_path.read_text(encoding="utf-8"))
                    smoke = {"verdict": stored.get("verdict"),
                             "headline": _smoke_mod().headline(stored),
                             "checked": stored.get("checked"), "seconds": stored.get("seconds")}
                except Exception:
                    smoke = {"verdict": "unchecked", "headline": "smoke report unreadable"}
            try:
                secrets = _secrets_mod().scan_bundle(child)
                secrets_row = {"ok": bool(secrets.get("ok")),
                               "count": len(secrets.get("findings") or []),
                               "line": (_secrets_mod().describe(secrets.get("findings") or [])
                                        if not secrets.get("ok") else "")}
            except Exception as exc:
                secrets_row = {"ok": None, "count": 0, "line": f"scan unavailable: {type(exc).__name__}"}
            rows.append({
                "name": name,
                "secrets": secrets_row,
                "smoke": smoke,
                "title": str(manifest.get("title") or name.replace("-", " ").replace("_", " ").title()),
                "description": " ".join(str(manifest.get("description") or "").split()),
                "version": str(manifest.get("version") or ""),
                "tools": list(manifest.get("provides_tools") or []),
                "hooks": list(manifest.get("provides_hooks") or []),
                "dir": str(child),
                "installed": (core.hermes_home() / "plugins" / name).exists(),
                "published": published,
                "validated": check.get("ok"),
                "validation": check.get("tail") or [],
                "files": len([p for p in child.rglob("*")
                              if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]),
            })
    _write_validation_cache(core, cache)
    return {"ok": True, "created": rows, "outbox": str(root)}


def _secrets_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_secrets_api", _PLUGIN_DIR / "secretscan.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _validation_cache(core) -> dict:
    path = core.state_dir() / "validation.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_validation_cache(core, cache: dict) -> None:
    path = core.state_dir() / "validation.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


EDITABLE = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".js", ".toml", ".cfg", ".ini"}
MAX_EDIT_BYTES = 262_144


def _bundle(name: str):
    core = _core()
    bundle = (core.state_dir() / "created" / name).resolve()
    root = (core.state_dir() / "created").resolve()
    if root not in bundle.parents:
        return None
    return bundle if (bundle / "plugin.yaml").exists() else None


@router.get("/created/files")
async def created_files(name: str = ""):
    return await asyncio.to_thread(_created_files, name)


def _created_files(name: str) -> dict:
    bundle = _bundle(name)
    if bundle is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    files = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.suffix not in EDITABLE:
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        files.append({"path": str(path.relative_to(bundle)), "size": path.stat().st_size})
    return {"ok": True, "name": name, "dir": str(bundle), "files": files}


@router.get("/created/file")
async def created_file(name: str = "", path: str = ""):
    return await asyncio.to_thread(_read_created_file, name, path)


def _read_created_file(name: str, path: str) -> dict:
    bundle = _bundle(name)
    if bundle is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    target = (bundle / path).resolve()
    if bundle != target and bundle not in target.parents:
        return {"ok": False, "error": "that path is outside the plugin"}
    if not target.is_file():
        return {"ok": False, "error": f"{path} is not a file"}
    if target.suffix not in EDITABLE:
        return {"ok": False, "error": f"{path} is not editable here"}
    if target.stat().st_size > MAX_EDIT_BYTES:
        return {"ok": False, "error": "file is too large to edit here"}
    return {"ok": True, "name": name, "path": path,
            "content": target.read_text(encoding="utf-8", errors="replace")}


@router.post("/created/file")
async def save_created_file(payload: dict | None = None):
    """Write an edit back, then re-validate so the tile cannot claim a state it lost."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    path = str(payload.get("path") or "").strip()
    content = payload.get("content")
    if not isinstance(content, str):
        return JSONResponse({"ok": False, "error": "content must be a string"}, status_code=400)
    return await asyncio.to_thread(_write_created_file, name, path, content)


def _write_created_file(name: str, path: str, content: str) -> dict:
    bundle = _bundle(name)
    if bundle is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    target = (bundle / path).resolve()
    if bundle != target and bundle not in target.parents:
        return {"ok": False, "error": "that path is outside the plugin"}
    if target.suffix not in EDITABLE:
        return {"ok": False, "error": f"{path} is not editable here"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    check = _creator_mod().validate_plugin(bundle)
    return {"ok": True, "name": name, "path": path, "bytes": len(content.encode()),
            "validation": {"ok": bool(check.get("ok")),
                           "tail": [line for line in (check.get("tail") or []) if line.strip()][-4:]},
            "validated": bool(check.get("ok"))}


@router.post("/created/uninstall")
async def uninstall_created(payload: dict | None = None):
    """Take the link back out of ~/.hermes/plugins. The bundle itself is left alone."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    return await asyncio.to_thread(_uninstall_created, name)


def _uninstall_created(name: str) -> dict:
    core = _core()
    out = _publish_mod().uninstall_local(name, core.hermes_home() / "plugins")
    if out.get("ok"):
        # A stale allow-list entry would point at a plugin that no longer exists.
        try:
            subprocess.run(["hermes", "plugins", "disable", name],
                           capture_output=True, text=True, timeout=90)
        except Exception:
            pass
    return out


@router.post("/created/remove")
async def remove_created(payload: dict | None = None):
    """Delete one generated bundle. Confined to the outbox; a publish is not a backup."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    bundle = _bundle(name)
    if bundle is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    installed = (_core().hermes_home() / "plugins" / name)
    if installed.is_symlink() or installed.exists():
        return {"ok": False, "error": f"{name} is installed — remove the link in ~/.hermes/plugins first"}
    import shutil as _shutil
    _shutil.rmtree(bundle)
    return {"ok": True, "removed": str(bundle)}


@router.post("/created/install")
async def install_created(payload: dict | None = None):
    """Link a generated plugin into the profile. Re-validates first; refuses to overwrite."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    return await asyncio.to_thread(_install_created, name)


def _install_created(name: str, force: bool = False) -> dict:
    core = _core()
    source = _bundle(name)          # resolves and confines to created/ — a `..` name is refused here
    if source is None:
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    # Validating proves the package is shaped right; smoke proves it runs. A tool that raises from
    # a stub body is installable and useless, which is exactly what nobody asked for.
    creator = _creator_mod()
    report = creator.smoke_plugin(source, live=False)
    if report.get("verdict") in ("broken", "scaffold") and not force:
        return {"ok": False, "smoke": report,
                "error": "this one does not run: " + creator._smoke_headline(report)
                         + " — try it out for the detail"}
    publish = _publish_mod()
    return publish.install_local(source, name, core.hermes_home() / "plugins",
                                 _creator_mod().validate_plugin)


def _publish_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_publish_api", _PLUGIN_DIR / "publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


JOBS: dict[str, dict] = {}
JOB_TTL_SECONDS = 3600


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for key in [k for k, v in JOBS.items() if v.get("started", 0) < cutoff]:
        JOBS.pop(key, None)


def _start_job(target, *args) -> str:
    """A thread that keeps this request's contextvars, so the profile scope rides along."""
    import contextvars

    job = uuid.uuid4().hex[:12]
    JOBS[job] = {"job": job, "ok": None, "stage": "starting", "stage_started": time.time(),
                 "result": None, "error": None, "steps": [], "started": time.time()}
    _prune_jobs()
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(target, job, *args), daemon=True).start()
    return job


@router.get("/jobs/{job}")
async def job_status(job: str):
    """One in-flight publish, as the page polls it."""
    entry = JOBS.get(job)
    if entry is None:
        return {"ok": False, "job": job, "error": "unknown or expired job", "stage": "gone"}
    return dict(entry)


@router.post("/created/publish")
async def publish_created(payload: dict | None = None):
    """Push a generated plugin to a public repo, pin its SHA, and write the catalog entry."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    open_pr = bool(payload.get("open_pr"))
    bundle = _bundle(name)          # same guard as install: never a raw join on a request field
    if bundle is None:
        return JSONResponse({"ok": False, "error": f"no generated plugin named {name!r}"},
                            status_code=404)
    job = _start_job(_publish_via_scope, bundle, name, owner, open_pr)
    return {"ok": True, "job": job, "stage": "starting"}


def _scope_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_scope_api", _PLUGIN_DIR / "scope.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _publish_via_scope(job: str, bundle, name: str, owner: str, open_pr: bool) -> None:
    # A bare thread starts with empty contextvars; this process serves several profiles.
    _scope_mod().run_in_scope(_publish_worker, job, bundle, name, owner, open_pr)


def _publish_worker(job: str, bundle, name: str, owner: str, open_pr: bool) -> None:
    entry = JOBS[job]
    try:
        publish = _publish_mod()
        entry["stage"] = "checking the package"
        manifest = _creator_mod().read_manifest(bundle)
        if not owner:
            owner = publish.gh_identity()["login"]
        entry["stage"] = "publishing"
        result = publish.publish(bundle, name, owner, manifest, open_pull_request=open_pr)
        entry["steps"] = result.get("steps") or []
        entry.update(ok=bool(result.get("ok")), stage="done" if result.get("ok") else "failed",
                     result=result, error=result.get("error"))
    except Exception as exc:
        entry.update(ok=False, stage="failed", error=f"{type(exc).__name__}: {exc}"[:400])
    finally:
        entry["finished"] = time.time()


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

    def payload() -> dict:
        catalog = core.load_catalog()
        return {"ok": True,
                "routes": sorted({getattr(r, "path", "").rsplit("/", 1)[-1] for r in router.routes} - {""}),
                "catalog_entries": len(catalog.get("entries") or []),
                "skills": len(core.scan_skills() or []),
                "created": str(core.state_dir() / "created")}

    return await asyncio.to_thread(payload)
