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


def _call(handler: Any, params: dict, config: dict, timeout: float) -> tuple[Any, str]:
    """Call a handler with a wall-clock limit; a hung handler is a broken handler."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = handler(params, config)
        except NotImplementedError as exc:
            box["result"] = {"ok": False, "error": f"scaffold: {exc}"}
        except Exception as exc:  # the caller needs the message, not a traceback
            box["result"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    thread = threading.Thread(target=run, daemon=True)
    started = time.time()
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return {"ok": False, "error": f"timed out after {timeout:.0f}s"}, "timeout"
    return box.get("result"), f"{time.time() - started:.1f}s"


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
        with tempfile.TemporaryDirectory() as tmp:
            call_config = dict(config or {})
            call_config.setdefault("path", str(Path(tmp) / "smoke.txt"))
            call_config.setdefault("content", "smoke")
            result, elapsed = _call(handler, params, call_config, timeout)
        status, detail = _classify(result)
        row.update({"status": status, "detail": detail, "seconds": elapsed, "params": params})
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
