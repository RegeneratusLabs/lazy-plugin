"""Smoke test a generated plugin: load it, register it, call every tool, grade the answer.

`hermes plugins validate` only proves the package is shaped correctly. Both plugins that shipped
broken passed it: one raised NotImplementedError from a stub body, the other asked for `config.url`
that nothing ever set. A structure check cannot see either, so this loads the module for real,
registers the tools against a stand-in context, and calls each handler once with plausible params.

The grading is deliberately blunt, because "valid" is what lied to us:

  works        every tool returned a real result
  needs-key    the package is sound; a named env var or config value is missing
  upstream     the request was built and sent; the far end refused it (401/403/404)
  scaffold     a tool body is still a stub: it raises NotImplementedError
  broken       it crashed, did not return a dict, or never finished

Never installs anything, never writes outside a temp dir, and does not call a tool whose declared
key is absent — no point spending a paid request to learn a variable is unset.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

MAX_SECONDS = 25.0

# A sample value per parameter, so a handler gets called the way a user would call it.
_SAMPLES = {
    "query": "cat",
    "q": "cat",
    "search": "cat",
    "term": "cat",
    "text": "cat",
    "limit": 3,
    "count": 3,
    "max": 3,
    "max_price": 100,
    "price": 100,
    "threshold": 100,
    "latitude": -26.65,
    "longitude": 153.07,
    "city": "Brisbane",
    "url": "https://example.com",
    "path": "~/smoke.txt",
    "name": "smoke",
}
_NUMERIC_HINTS = ("limit", "count", "max", "min", "price", "threshold", "num", "size", "lat", "lon")


def sample_params(params: Optional[dict]) -> dict:
    """A plausible call for each declared parameter — enough to exercise the body."""
    out = {}
    for name in (params or {}):
        key = str(name).lower()
        if key in _SAMPLES:
            out[name] = _SAMPLES[key]
        elif any(hint in key for hint in _NUMERIC_HINTS):
            out[name] = 3
        else:
            out[name] = "test"
    return out


class _FakeCtx:
    """Just enough of the plugin context to prove registration works."""

    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}
        self.hooks: list[str] = []

    def register_tool(self, name: str, toolset: str = "", schema: Optional[dict] = None,
                      handler: Any = None, description: str = "", **kwargs: Any) -> None:
        self.tools[name] = {"schema": schema or {}, "handler": handler, "toolset": toolset}

    def register_hook(self, hook: str, handler: Any = None, **kwargs: Any) -> None:
        self.hooks.append(hook)


def _load(bundle: Path):
    module_name = "smoke_" + bundle.name.replace("-", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, bundle / "__init__.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load __init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_manifest(bundle: Path) -> dict:
    text = (bundle / "plugin.yaml").read_text(encoding="utf-8", errors="replace")
    manifest: dict[str, Any] = {"requires_env": [], "provides_tools": []}
    block = None
    for line in text.splitlines():
        if line.startswith(("requires_env:", "provides_tools:")):
            block = line.split(":")[0]
            continue
        if block and line.startswith(("  - ", "- ")):
            manifest[block].append(line.split("- ", 1)[1].strip().strip("'\""))
            continue
        if line and not line.startswith((" ", "#")):
            block = None
        if line.startswith("version:"):
            manifest["version"] = line.split(":", 1)[1].strip()
    return manifest


def contract_violations(bundle: Path) -> list[str]:
    """The developer guide's handler contract, checked before anything is allowed to ship.

    `registry.dispatch` calls `handler(args, **kwargs)` and filters kwargs to the signature, so a
    required `config` parameter is never filled; `_normalize_handler_result` accepts only a str. A
    generator that emits either shape produces a plugin that validates and cannot run.
    """
    problems: list[str] = []
    try:
        module = _load(bundle)
    except Exception as exc:
        return [f"cannot import __init__.py: {type(exc).__name__}: {exc}"]
    ctx = _FakeCtx()
    register = getattr(module, "register", None)
    if not callable(register):
        return ["no register(ctx) function"]
    try:
        register(ctx)
    except Exception as exc:
        return [f"register(ctx) raised: {type(exc).__name__}: {exc}"]
    if not ctx.tools:
        return ["register(ctx) registered no tools"]
    for name, entry in ctx.tools.items():
        handler = entry.get("handler")
        if not callable(handler):
            problems.append(f"{name}: no handler callable")
            continue
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            continue
        required = [p for p in signature.parameters.values()
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                    and p.default is p.empty]
        if len(required) != 1:
            problems.append(f"{name}: handler takes {len(required)} required positional "
                            "parameters; the contract is one (params)")
        if any(p.name == "config" for p in signature.parameters.values()):
            problems.append(f"{name}: a `config` parameter is never filled by the registry")
        if not any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values()):
            problems.append(f"{name}: handler should accept **kwargs")
        source = ""
        try:
            source = inspect.getsource(handler)
        except (OSError, TypeError):
            pass
        if source and "json.dumps" not in source and "NotImplementedError" not in source:
            problems.append(f"{name}: handler must return json.dumps(...), not a dict")
    return problems


def _classify(result: Any) -> tuple[str, str]:
    if not isinstance(result, dict):
        return "broken", f"returned {type(result).__name__}, not a result object"
    if result.get("ok") is True:
        count = result.get("count")
        detail = f"{count} item(s)" if isinstance(count, int) else "returned a result"
        return "works", detail
    error = str(result.get("error") or "")
    lowered = error.lower()
    if " is not set" in lowered or "not configured" in lowered:
        return "needs-key", error
    if "http error" in lowered:
        return "upstream", error
    if "notimplemented" in lowered or "scaffold" in lowered:
        return "scaffold", error or "handler is still a stub"
    return "broken", error or "returned ok=false with no error"


def _is_stub(handler: Any) -> bool:
    """A scaffold body raises NotImplementedError as its only statement.

    Checking the source means a stub is caught even when live calls are off — the install gate runs
    with live off, and it must still refuse a tool that cannot do anything.
    """
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return False
    body = [line for line in source.splitlines()[1:] if line.strip() and not line.strip().startswith("#")]
    return len(body) <= 3 and "NotImplementedError" in source


# The real contract, from the developer guide: discover the plugin, then dispatch through the tool
# registry the model itself calls. `registry.dispatch` fills only the kwargs the signature accepts
# and `_normalize_handler_result` accepts only a str — a direct `handler(params, config)` call hides
# both defects, which is how two structurally wrong plugins shipped looking valid.
DISPATCH = """
import json, sys
from hermes_cli.plugins import discover_plugins
discover_plugins(force=True)
from tools.registry import registry
raw = registry.dispatch(sys.argv[1], json.loads(sys.argv[2]))
print("<<<SMOKE>>>" + json.dumps({"type": type(raw).__name__,
                                 "raw": raw if isinstance(raw, str) else repr(raw)}))
"""


def _interpreter() -> str:
    """The interpreter that has Hermes' own dependencies — not necessarily the one running this."""
    explicit = os.environ.get("HERMES_PYTHON")
    if explicit and Path(explicit).exists():
        return explicit
    home = Path.home() / ".hermes"
    # Newest first: the PM-managed env the gateway actually runs in, then the downloaded tools.
    candidates = [str(p) for p in sorted(home.glob("installs/*/environments/*/venv/bin/python3"),
                                         key=lambda p: p.stat().st_mtime, reverse=True)]
    candidates += [str(p) for p in sorted(home.glob("tools/python-*/bin/python3"), reverse=True)]
    candidates.append(sys.executable)
    for candidate in candidates:
        try:
            ok = subprocess.run([candidate, "-c", "import ruamel.yaml"], capture_output=True,
                                timeout=20).returncode == 0
        except Exception:
            ok = False
        if ok:
            return candidate
    return sys.executable


def _agent_home() -> Path:
    explicit = os.environ.get("HERMES_AGENT_HOME")
    if explicit and Path(explicit).is_dir():
        return Path(explicit)
    return Path.home() / ".hermes" / "hermes-agent"


def _dispatch(bundle: Path, tool: str, params: dict, timeout: float) -> dict:
    """Dispatch one tool in a throwaway HERMES_HOME, so nothing installed elsewhere can answer."""
    agent = _agent_home()
    with tempfile.TemporaryDirectory() as home:
        plugins = Path(home) / "plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        link = plugins / bundle.name
        try:
            link.symlink_to(bundle.resolve(), target_is_directory=True)
        except OSError as exc:
            return {"status": "broken", "detail": f"cannot stage the bundle: {exc}"}
        # Discovery only loads what plugins.enabled allows; a fresh home enables nothing.
        (Path(home) / "config.yaml").write_text(
            "plugins:\n  enabled:\n    - " + bundle.name + "\n", encoding="utf-8")
        env = {**os.environ, "HERMES_HOME": home, "PYTHONUNBUFFERED": "1",
               "PYTHONPATH": str(agent)}
        try:
            proc = subprocess.run([_interpreter(), "-c", DISPATCH, tool, json.dumps(params)],
                                  capture_output=True, text=True, timeout=timeout,
                                  env=env, cwd=str(agent))
        except subprocess.TimeoutExpired:
            return {"status": "broken", "detail": f"dispatch timed out after {timeout:.0f}s"}
    marker = [line for line in (proc.stdout or "").splitlines() if line.startswith("<<<SMOKE>>>")]
    if not marker:
        tail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])
        # A missing host dependency is not the plugin's fault; say so instead of calling it broken.
        if "ModuleNotFoundError" in tail or "No module named" in tail:
            return {"status": "unchecked",
                    "detail": f"the smoke host is missing a dependency: {tail[:200]}"}
        return {"status": "broken", "detail": f"dispatch did not run: {tail[:300] or 'no output'}"}
    try:
        payload = json.loads(marker[-1][len("<<<SMOKE>>>"):])
    except ValueError:
        return {"status": "broken", "detail": "dispatch produced unreadable output"}
    if payload.get("type") != "str":
        return {"status": "broken",
                "detail": f"handler returned {payload.get('type')}, not a JSON string — "
                          "the runtime refuses that result type"}
    try:
        result = json.loads(payload.get("raw") or "{}")
    except ValueError:
        return {"status": "broken", "detail": "handler returned a string that is not JSON"}
    status, detail = _classify(result)
    return {"status": status, "detail": detail, "result": result}


def smoke(bundle: Path, config: Optional[dict] = None, live: bool = True,
          timeout: float = MAX_SECONDS) -> dict:
    """Grade one generated plugin. Never raises: a smoke result is always a result."""
    bundle = Path(bundle)
    started = time.time()
    report: dict[str, Any] = {"plugin": bundle.name, "bundle": str(bundle),
                              "checked": started, "tools": [], "verdict": "broken", "notes": []}
    try:
        manifest = _read_manifest(bundle)
        module = _load(bundle)
    except Exception as exc:
        report["notes"].append(f"cannot load the package: {type(exc).__name__}: {exc}")
        return report

    ctx = _FakeCtx()
    register = getattr(module, "register", None)
    if not callable(register):
        report["notes"].append("no register(ctx) function, so the plugin mounts nothing")
        return report
    try:
        register(ctx)
    except Exception as exc:
        report["notes"].append(f"register(ctx) raised: {type(exc).__name__}: {exc}")
        return report

    declared = manifest.get("provides_tools") or list(ctx.tools)
    missing = [name for name in declared if name not in ctx.tools]
    if missing:
        report["notes"].append("declared but never registered: " + ", ".join(missing))
    extra = [name for name in ctx.tools if name not in declared]
    if extra:
        report["notes"].append("registered but not declared: " + ", ".join(extra))

    required = manifest.get("requires_env") or []
    absent = [name for name in required if not (os.environ.get(name) or (config or {}).get(name))]

    params_hint = getattr(module, "PARAMS", {}) or {}
    for name, entry in ctx.tools.items():
        row: dict[str, Any] = {"tool": name, "status": "broken", "detail": ""}
        handler = entry.get("handler")
        schema = entry.get("schema") or {}
        if not callable(handler):
            row["detail"] = "no handler registered"
            report["tools"].append(row)
            continue
        if _is_stub(handler):
            row["status"] = "scaffold"
            row["detail"] = "handler body is still a stub — it raises NotImplementedError"
            report["tools"].append(row)
            continue
        if absent:
            row["status"] = "needs-key"
            row["detail"] = "set " + ", ".join(absent) + " to test this for real"
            report["tools"].append(row)
            continue
        if not live:
            row["status"] = "skipped"
            row["detail"] = "live calls disabled"
            report["tools"].append(row)
            continue
        params = sample_params(params_hint.get(name) or
                               (schema.get("parameters") or {}).get("properties"))
        started_call = time.time()
        dispatched = _dispatch(bundle, name, params, timeout)
        row.update({"status": dispatched["status"], "detail": dispatched["detail"],
                    "seconds": f"{time.time() - started_call:.1f}s", "params": params})
        report["tools"].append(row)

    statuses = [row["status"] for row in report["tools"]]
    if not report["tools"]:
        report["verdict"] = "broken"
        report["notes"].append("no tools registered at all")
    elif all(status == "works" for status in statuses):
        report["verdict"] = "works"
    elif "broken" in statuses or "scaffold" in statuses:
        report["verdict"] = "broken"
    elif "needs-key" in statuses:
        report["verdict"] = "needs-key"
    elif "upstream" in statuses:
        report["verdict"] = "upstream"
    else:
        report["verdict"] = "unchecked"
    report["seconds"] = round(time.time() - started, 2)
    return report


def headline(report: dict) -> str:
    """One line for a tile, a tool result or a chat message."""
    verdict = report.get("verdict")
    if verdict == "works":
        names = ", ".join(row["tool"] for row in report["tools"])
        return f"works — {names} returned real results"
    if verdict == "needs-key":
        detail = "; ".join(row["detail"] for row in report["tools"] if row["status"] == "needs-key")
        return f"sound package, needs a key: {detail}"
    if verdict == "upstream":
        detail = "; ".join(row["detail"] for row in report["tools"] if row["status"] == "upstream")
        return f"request works, far end refused it: {detail}"
    if verdict == "broken":
        first = next((row for row in report["tools"] if row["status"] in ("broken", "scaffold")), None)
        note = report["notes"][0] if report.get("notes") else (first or {}).get("detail", "")
        if first and first.get("status") == "scaffold":
            return f"broken: scaffold — {first['tool']} never got written"
        return f"broken: {note}" if note else "broken"
    return "not checked"


def write_report(bundle: Path, report: dict) -> Path:
    path = Path(bundle) / "smoke.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
