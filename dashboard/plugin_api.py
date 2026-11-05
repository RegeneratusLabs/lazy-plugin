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
import sys
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
            rows.append({
                "name": name,
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


@router.post("/create/answers")
async def create_from_answers(payload: dict | None = None):
    """Questionnaire path. Deterministic, so it works without any provider credential."""
    payload = payload or {}
    creator = _creator_mod()
    drafted = creator.spec_from_answers(payload)
    if not drafted.get("ok"):
        return JSONResponse({"ok": False, "stage": drafted.get("stage"),
                             "problems": drafted.get("problems") or []}, status_code=400)
    return await asyncio.to_thread(creator.create, drafted["spec"])


@router.post("/create/prefill")
async def prefill_answers(payload: dict | None = None):
    """A sentence in, questionnaire answers out. No model, so it works on any surface."""
    payload = payload or {}
    idea = str(payload.get("idea") or "")
    creator = _creator_mod()
    return {"ok": True, "answers": creator.answers_from_idea(idea)}


@router.get("/questions")
async def questions():
    """The questionnaire is data, so the page cannot drift from the spec it feeds."""
    return {
        "ok": True,
        "questions": [
            {"id": "purpose", "label": "What should it do?", "type": "text", "rows": 2,
             "placeholder": "Watch GPU prices and tell me when one drops under $600",
             "required": True},
            {"id": "action", "label": "How does it do that?", "type": "select",
             "options": ["fetch a URL", "read or write a file", "run a command", "just scaffold it"],
             "default": "fetch a URL"},
            {"id": "target", "label": "Where?", "type": "text",
             "placeholder": "https://example.com/deals.json, ~/prices.json, or `ls -la`"},
            {"id": "returns", "label": "What should it give back?", "type": "text",
             "placeholder": "the cheapest matching listing, with its price and link"},
            {"id": "trigger", "label": "When does it run?", "type": "select",
             "options": ["when I ask", "after every session"], "default": "when I ask"},
            {"id": "secret", "label": "Needs a key or login?", "type": "text",
             "placeholder": "API_KEY (leave empty if not)"},
            {"id": "category", "label": "Shelf", "type": "select",
             "options": ["tools", "automation", "web", "memory", "voice", "models", "general"],
             "default": "tools"},
        ],
    }


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


@router.post("/created/install")
async def install_created(payload: dict | None = None):
    """Link a generated plugin into the profile. Re-validates first; refuses to overwrite."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    return await asyncio.to_thread(_install_created, name)


def _install_created(name: str) -> dict:
    core = _core()
    source = core.state_dir() / "created" / name
    if not name or not (source / "plugin.yaml").exists():
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    publish = _publish_mod()
    return publish.install_local(source, name, core.hermes_home() / "plugins",
                                 _creator_mod().validate_plugin)


def _publish_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_publish_api", _PLUGIN_DIR / "publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@router.post("/created/publish")
async def publish_created(payload: dict | None = None):
    """Push a generated plugin to a public repo, pin its SHA, and write the catalog entry."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    open_pr = bool(payload.get("open_pr"))
    bundle = _core().state_dir() / "created" / name
    if not name or not (bundle / "plugin.yaml").exists():
        return JSONResponse({"ok": False, "error": f"no generated plugin named {name!r}"},
                            status_code=404)
    job = uuid.uuid4().hex[:12]
    JOBS[job] = {"job": job, "ok": None, "stage": "starting", "result": None, "error": None,
                 "steps": [], "started": time.time()}
    _start_job_thread(_run_publish, job, bundle, name, owner, open_pr)
    return {"ok": True, "job": job, "stage": "starting"}


def _run_publish(job: str, bundle, name: str, owner: str, open_pr: bool) -> None:
    _scope_mod().run_in_scope(_publish_worker, JOBS[job], bundle, name, owner, open_pr)


def _publish_worker(entry: dict, bundle, name: str, owner: str, open_pr: bool) -> None:
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


@router.post("/created/share")
async def share_created(payload: dict | None = None):
    """Write the marketplace entry, the PR steps and a tarball you can hand to anyone."""
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    return await asyncio.to_thread(_share_created, name)


def _share_created(name: str) -> dict:
    core = _core()
    bundle = core.state_dir() / "created" / name
    if not name or not (bundle / "plugin.yaml").exists():
        return {"ok": False, "error": f"no generated plugin named {name!r}"}
    manifest = _creator_mod().read_manifest(bundle)

    entry = {
        "name": name,
        "repo": "https://github.com/<you>/<repo>",
        "sha": "<full 40-character commit sha>",
        "version": str(manifest.get("version") or "0.1.0"),
        "title": name.replace("-", " ").title(),
        "description": str(manifest.get("description") or "")[:400],
        "maintainer": "<your-github-handle>",
        "tier": "community",
        "category": "tools",
        "docs_url": "https://github.com/<you>/<repo>#readme",
        "capabilities": {
            "provides_tools": manifest.get("provides_tools") or [],
            "provides_hooks": manifest.get("provides_hooks") or [],
            "provides_middleware": [],
            "requires_env": manifest.get("requires_env") or [],
        },
        "requires_hermes": ">=0.21.6",
    }
    catalog_dir = bundle / "plugin-catalog"
    catalog_dir.mkdir(exist_ok=True)
    entry_path = catalog_dir / f"{name}.yaml"
    entry_path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")

    submission = bundle / "SUBMISSION.md"
    submission.write_text(
        f"""# Sharing `{name}`

## 1. Publish the repo

```bash
cd {bundle}
git init -q && git add -A && git commit -qm 'Add {name} plugin'
# create a public repo you own, then:
git remote add origin <your repo url> && git push -u origin main
git rev-parse HEAD    # paste this full 40-character sha into plugin-catalog/{name}.yaml
```

## 2. Validate

```bash
hermes plugins validate {bundle} --install-deps
```

## 3. Submit to the catalog

- Fork https://github.com/NousResearch/hermes-agent
- Add `plugin-catalog/{name}.yaml` (generated beside this file)
- Open the PR. Human-merged by design: presence in the catalog is the trust signal.

## 4. Or just hand it to someone

```bash
tar -czf {name}.tar.gz -C {bundle} .
```

Rules reviewers will check: exact SHA pin, declared capabilities matching what it registers,
no self-updating code, owner-or-major-contributor submission.
""", encoding="utf-8")

    tarball = None
    try:
        # outside the bundle, or tar warns about the archive changing while it reads it
        tarball = str(bundle.parent / f"{name}.tar.gz")
        subprocess.run(["tar", "-czf", tarball, "-C", str(bundle), "."],
                       check=True, capture_output=True, timeout=120)
    except Exception:
        tarball = None

    return {"ok": True, "name": name, "dir": str(bundle),
            "catalog_entry": str(entry_path), "submission": str(submission),
            "tarball": tarball,
            "files": [f"plugin-catalog/{name}.yaml", "SUBMISSION.md"] + ([f"{name}.tar.gz"] if tarball else [])}


_KEY_UNREADABLE = ("this process cannot read the provider API key — restart the gateway "
                   "(`hermes gateway " + "restart`) and try again")

JOBS: dict[str, dict] = {}


@router.post("/create")
async def create_plugin(payload: dict | None = None):
    """Start a build. Returns a job id — a model call plus validation outlives any HTTP request."""
    payload = payload or {}
    idea = str(payload.get("idea") or "").strip()
    kind = str(payload.get("source_kind") or "").strip()
    source = str(payload.get("source_name") or "").strip()
    if not idea and source:
        idea = f"Turn this {kind} into a plugin: {source}"
    if len(idea) < 10:
        return JSONResponse({"ok": False, "stage": "input",
                             "problems": ["describe the plugin, or pick a skill or cron job"]},
                            status_code=400)
    job = uuid.uuid4().hex[:12]
    JOBS[job] = {"job": job, "ok": None, "stage": "starting", "result": None, "error": None,
                 "started": time.time()}
    _start_job_thread(_run_create, job, idea, kind, source)
    return {"ok": True, "job": job, "stage": "starting"}


def _start_job_thread(target, *args) -> None:
    """A thread that keeps this request's contextvars, so the profile scope rides along."""
    import contextvars

    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(target, *args), daemon=True).start()


def _scope_mod():
    spec = importlib.util.spec_from_file_location("lazyplugin_scope_api", _PLUGIN_DIR / "scope.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _run_create(job: str, idea: str, kind: str, source: str) -> None:
    # a bare thread starts with empty contextvars, and this process serves several profiles
    _scope_mod().run_in_scope(_create_worker, JOBS[job], idea, kind, source)


def _create_worker(entry: dict, idea: str, kind: str, source: str) -> None:
    try:
        entry["stage"] = "reading what you picked"
        context = _source_context(kind, source)
        ctx, meta = _find_ctx()
        llm = getattr(ctx, "llm", None) if ctx is not None else None
        creator = _creator_mod()
        entry["stage"] = "asking the model for a spec"
        if _scope_mod().secret_probe("OPENCODE_GO_API_KEY") is False:
            entry.update(ok=False, stage="failed", error=_KEY_UNREADABLE)
            return
        drafted = creator.draft_spec(idea, llm, context)
        if not drafted.get("ok"):
            drafted["ctx"] = meta
            entry.update(ok=False, stage="refused", result=drafted,
                         error=" ".join(drafted.get("problems") or []) or "the model gave no usable spec")
            return
        entry["stage"] = "writing the files and validating"
        written = creator.create(drafted["spec"])
        written["draft"] = {"stage": drafted.get("stage"), "meta": drafted.get("meta")}
        written["source"] = {"kind": kind, "name": source, "chars": len(context)}
        entry.update(ok=bool(written.get("ok")), stage="done", result=written,
                     error=None if written.get("ok") else "the generated plugin did not validate")
    except Exception as exc:
        entry.update(ok=False, stage="failed", error=f"{type(exc).__name__}: {exc}"[:400])
    finally:
        entry["finished"] = time.time()
        cutoff = time.time() - 3600
        for key in [k for k, v in JOBS.items() if v.get("started", 0) < cutoff]:
            JOBS.pop(key, None)


@router.get("/create/job/{job}")
async def create_job(job: str):
    entry = JOBS.get(job)
    if entry is None:
        return {"ok": False, "job": job, "error": "unknown or expired job", "stage": "gone"}
    return entry


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
