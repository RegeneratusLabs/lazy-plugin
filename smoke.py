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

The live run has a second gate, because the thing being tried out was drafted by a model: a declared
credential is only ever carried to a plain public https host the handler's own code names, and
Hermes' own keys (provider keys, gateway tokens, dashboard secrets) are never carried anywhere. A
spec that asks for one is refused with the reason instead of being run.
"""

from __future__ import annotations

import importlib.util
import datetime
import ipaddress
import re
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

MAX_SECONDS = 25.0

# A sample value per parameter, so a handler gets called the way a user would call it.
_SAMPLES = {
    # shape matters: a date sent as "test" earns a 404 from a real API and the receipt blames the
    # far end for our own sample value
    "date": datetime.date.today().isoformat(),
    "start_date": datetime.date.today().isoformat(),
    "end_date": (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
    "since": datetime.date.today().isoformat(),
    "until": (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
    "day": datetime.date.today().isoformat(),
    "month": datetime.date.today().month,
    "year": datetime.date.today().year,
    "domain": "example.com",
    "host": "example.com",
    "hostname": "example.com",
    "url": "https://example.com",
    "endpoint": "https://example.com",
    "email": "smoke@example.com",
    "city": "Brisbane",
    "country": "AU",
    "country_code": "AU",
    "currency": "AUD",
    "base": "AUD",
    "quote": "USD",
    "symbol": "AUDUSD",
    "ticker": "BHP",
    "coin": "bitcoin",
    "pair": "BTCUSDT",
    "postcode": "4551",
    "zip": "4551",
    "query": "cat nip",
    "q": "cat nip",
    "search": "cat nip",
    "term": "cat nip",
    "text": "cat nip",
    "id": "1",
    "slug": "smoke",
    "limit": 3,
    "count": 3,
    "max": 3,
    "max_price": 100,
    "price": 100,
    "threshold": 100,
    "budget": 100,
    "latitude": -26.65,
    "longitude": 153.07,
    "path": "smoke.txt",
    "name": "smoke",
}
_NUMERIC_HINTS = ("limit", "count", "max", "min", "price", "threshold", "num", "size", "lat", "lon")


def _sample_write(handler: Any, params: dict) -> dict:
    """Give a write-capable file tool a write, so the try-out proves the round trip.

    Without this the sample only reads a file that cannot exist yet and the receipt says broken —
    which blames the template for the order of the test.
    """
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return params
    if '"write"' in source or "'write'" in source:
        return {**params, "write": True, "content": "lazy plugin smoke"}
    return params


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


def _declared_env(bundle: Path) -> list:
    """The env var names this plugin's own manifest asks for. Nothing else is passed through."""
    try:
        text = (Path(bundle) / "plugin.yaml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names, in_block = [], False
    for line in text.splitlines():
        if re.match(r"^requires_env\s*:", line):
            in_block = True
            continue
        if in_block:
            found = re.match(r"^\s*-\s*([A-Z][A-Z0-9_]*)\s*$", line)
            if found:
                names.append(found.group(1))
            elif line.strip():
                in_block = False
    return names


# ---------- what a live run may carry, and where

# Hermes' own credentials. A generated plugin must never be handed one, because a spec chooses BOTH
# the variable and the URL, and the handler spends the one at the other — so "try it out" would post
# whatever the draft asked for.
_STATIC_HOST_SECRETS = frozenset({
    # provider keys, in case the registry cannot be imported
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY",
    "TOGETHER_API_KEY", "NOUS_API_KEY", "HF_TOKEN", "HUGGINGFACE_API_KEY", "MINIMAX_API_KEY",
    "ELEVENLABS_API_KEY", "EXA_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY",
    # Tier-1 infrastructure secrets: no generated child ever needs them
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_APP_PRIVATE_KEY_PATH", "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET",
    "GATEWAY_RELAY_SECRET", "GATEWAY_RELAY_DELIVERY_KEY", "EMAIL_PASSWORD",
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "DAYTONA_API_KEY",
})

_PRIVATE_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".onion")


def _host_secret_names() -> frozenset:
    """Every env name Hermes itself spends a credential under.

    Provider keys come from the provider registry Hermes routes with — the same authority its own
    environment policy reads — so a new provider is covered without a line here. The static set is
    the Tier-1 infrastructure list plus a fallback for a checkout that cannot import the registry.
    """
    names = set(_STATIC_HOST_SECRETS)
    try:
        from hermes_cli.auth import PROVIDER_REGISTRY

        for config in PROVIDER_REGISTRY.values():
            names.update(getattr(config, "api_key_env_vars", ()) or ())
    except Exception:
        pass
    return frozenset(str(name).upper() for name in names)


def is_host_credential(name: str) -> bool:
    """True when *name* is one of Hermes' own credentials (or any of its internals)."""
    upper = str(name or "").strip().upper()
    return bool(upper) and (upper.startswith("HERMES_") or upper in _host_secret_names())


def egress_problem(url: str) -> str:
    """Why a credential may not be carried to *url*; '' when the destination is a public https host.

    A model drafts both ends of this trip, so the destination is checked before anything is spent:
    https only, no loopback, no private or link-local address (169.254.169.254 included), no
    dot-local name, and a name has to resolve somewhere public to count.
    """
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return "unreadable url"
    scheme = (parts.scheme or "").lower()
    if scheme != "https":
        return f"{scheme or 'no'} scheme, not https"
    host = (parts.hostname or "").strip().strip(".").lower()
    if not host:
        return "no host"
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return f"{host} is a local name"
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except Exception:
            addresses = []
    for address in addresses:
        if (address.is_loopback or address.is_private or address.is_link_local
                or address.is_multicast or address.is_reserved or address.is_unspecified):
            return f"{host} is {address}"
    return ""


def _tool_urls(handler: Any) -> list:
    """Every http(s) URL literal in the handler's own code: where the spec said it would go.

    A bare scheme prefix ("https://" from the template's own scheme repair) is not a destination, so
    a candidate only counts when it parses to a host.
    """
    found, seen = [], set()

    def walk(code: Any) -> None:
        for const in getattr(code, "co_consts", ()) or ():
            if isinstance(const, str):
                text = const.strip()
                if text.lower().startswith(("http://", "https://")) and text not in seen:
                    seen.add(text)
                    try:
                        if urllib.parse.urlsplit(text).hostname:
                            found.append(text)
                    except ValueError:
                        pass
            elif hasattr(const, "co_consts"):
                walk(const)

    walk(getattr(handler, "__code__", None))
    return found


def dispatch_refusal(bundle: Path, handler: Any) -> str:
    """'' when the live call may go ahead; otherwise the sentence saying why it must not.

    With no declared credential there is nothing of the host's to leak, so the call is the ordinary
    risk the user took by pressing try-out. With one, the destination has to be checkable: a name
    the code actually contains, https, public.
    """
    declared = _declared_env(bundle)
    if not declared:
        return ""
    blocked = [name for name in declared if is_host_credential(name)]
    if blocked:
        return (f"{', '.join(blocked)} is Hermes' own credential — a generated plugin never gets "
                "one, so it was not called")
    urls = _tool_urls(handler)
    if not urls:
        return (f"{', '.join(declared)} would be sent to a host the handler never names — "
                "not called")
    for url in urls:
        problem = egress_problem(url)
        if problem:
            return f"{', '.join(declared)} would be sent to {url} ({problem}) — not called"
    return ""


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
        # Generated code runs in here. It gets the variables it declared and nothing else — not the
        # gateway's provider keys, not its GitHub token. Belt and braces with dispatch_refusal():
        # even if a caller reached this without checking the destination, a Hermes credential in a
        # declared list is dropped here rather than exported.
        keep = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM"}
        env = {name: os.environ[name] for name in keep if name in os.environ}
        env.update({"HERMES_HOME": home, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(agent)})
        for name in _declared_env(bundle):
            if name in os.environ and not is_host_credential(name):
                env[name] = os.environ[name]
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


def smoke(bundle: Path, config: Optional[dict] = None, live: bool = False,
          timeout: float = MAX_SECONDS) -> dict:
    """Grade one generated plugin. Never raises: a smoke result is always a result.

    live defaults to False: dispatch executes generated code and spends URLs, so it only happens when
    a caller asks — the page's try-it button, or a test proving the gate.
    """
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
        refusal = dispatch_refusal(bundle, handler)
        if refusal:
            # A model drafted both the variable and the URL, so the try-out is where a key would
            # leave the machine. Not called is the whole point of the gate, and the receipt says
            # which credential and which host so the reader can judge the draft.
            row["status"] = "refused"
            row["detail"] = refusal
            report["tools"].append(row)
            continue
        params = _sample_write(handler, sample_params(
            params_hint.get(name) or (schema.get("parameters") or {}).get("properties")))
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
    elif "broken" in statuses:
        report["verdict"] = "broken"
    elif "scaffold" in statuses:
        # A handler nobody wrote is unfinished work, not a failure to load. Grading it "broken" made
        # a green validation line sit above a red receipt, which reads as a lie.
        report["verdict"] = "scaffold"
    elif "refused" in statuses:
        # Nothing was called and nothing was wrong with the code: the try-out would have posted a
        # credential somewhere it does not belong.
        report["verdict"] = "refused"
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
        return f"purrs — {names} came back with real results"
    if verdict == "needs-key":
        detail = "; ".join(row["detail"] for row in report["tools"] if row["status"] == "needs-key")
        return f"solid build, just wants a key: {detail}"
    if verdict == "upstream":
        detail = "; ".join(row["detail"] for row in report["tools"] if row["status"] == "upstream")
        return f"our side works, the far end turned us away: {detail}"
    if verdict == "scaffold":
        stub = next((row for row in report["tools"] if row["status"] == "scaffold"), None)
        return f"half-built — nothing was ever written in {stub['tool'] if stub else 'it'}"
    if verdict == "refused":
        detail = "; ".join(row["detail"] for row in report["tools"] if row["status"] == "refused")
        return f"not tried out — {detail}"
    if verdict == "broken":
        first = next((row for row in report["tools"] if row["status"] in ("broken", "scaffold")), None)
        note = report["notes"][0] if report.get("notes") else (first or {}).get("detail", "")
        if first and first.get("status") == "scaffold":
            return f"half-built — nothing was ever written in {first['tool']}"
        return f"broken: {note}" if note else "broken"
    return "not tried out yet — press try it to call each tool for real"


def write_report(bundle: Path, report: dict) -> Path:
    path = Path(bundle) / "smoke.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
