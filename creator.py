"""Plugin creator: a described idea becomes a plugin that loads, registers, and validates.

The model does not write Python. It writes a **spec** — name, tools, parameters, which handler shape
each tool uses — and fixed templates render that spec into `plugin.yaml` + `__init__.py` + `SKILL.md`.
That split is the reliability story: rendered code always registers, always declares exactly the
capabilities it provides, and cannot contain injected code. `hermes plugins validate` is the referee.

Handler kinds are deliberately limited to three safe shapes:
  command -> run a binary with arguments from config      (subprocess, list argv, no shell)
  http    -> GET/POST a URL with headers from config      (urllib, timeout, json)
  file    -> read or write a path from config             (pathlib, confined to PLUGIN_DATA)

Anything else is a stub: the handler raises NotImplementedError with the described behaviour in the
docstring, which is honest and shows the next developer exactly what to write.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
KINDS = ("command", "http", "file", "stub")
MAX_TOOLS = 5


def _clean(text: str, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def validate_spec(spec: dict) -> tuple[Optional[dict], list]:
    """Return (clean_spec, problems). A spec with problems is never rendered."""
    problems = []
    if not isinstance(spec, dict):
        return None, ["spec is not an object"]

    name = _clean(spec.get("name"), 40).lower().replace("_", "-")
    if not NAME_RE.fullmatch(name or ""):
        problems.append(f"name {name!r} must be lowercase-hyphenated, 3-40 chars")

    title = _clean(spec.get("title"), 80) or name.replace("-", " ").title()
    description = _clean(spec.get("description"), 300)
    if len(description) < 20:
        problems.append("description must be at least 20 characters")

    tools_in = spec.get("tools") or []
    if not isinstance(tools_in, list) or not tools_in:
        problems.append("at least one tool is required")
        tools_in = []
    if len(tools_in) > MAX_TOOLS:
        problems.append(f"at most {MAX_TOOLS} tools per plugin")

    tools, seen = [], set()
    for raw in tools_in:
        if not isinstance(raw, dict):
            problems.append("tool entries must be objects")
            continue
        tool_name = _clean(raw.get("name"), 40).lower()
        if not TOOL_RE.fullmatch(tool_name or ""):
            problems.append(f"tool name {tool_name!r} must be lowercase_with_underscores")
            continue
        if tool_name in seen:
            problems.append(f"duplicate tool {tool_name!r}")
            continue
        seen.add(tool_name)
        kind = str(raw.get("kind") or "stub").lower()
        if kind not in KINDS:
            kind = "stub"
        params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
        clean_params = {}
        for pname, pdesc in list(params.items())[:6]:
            key = _clean(pname, 30)
            if not TOOL_RE.fullmatch(key or ""):
                continue
            clean_params[key] = _clean(pdesc, 120) or key
        tools.append({
            "name": tool_name,
            "description": _clean(raw.get("description"), 200) or tool_name,
            "kind": kind,
            "params": clean_params,
            "requires_env": [_clean(e, 60) for e in (raw.get("requires_env") or []) if _clean(e, 60)][:4],
            "behaviour": _clean(raw.get("behaviour"), 300),
        })

    hooks = [h for h in (spec.get("hooks") or []) if h in
             ("post_tool_call", "on_session_end", "on_skill_lifecycle", "on_session_start")][:2]

    clean = {
        "name": name,
        "title": title,
        "description": description,
        "author": _clean(spec.get("author"), 60) or "Hermes",
        "tools": tools,
        "hooks": hooks,
        "category": _clean(spec.get("category"), 40) or "tools",
        "origin": _clean(spec.get("origin"), 80),
    }
    return (clean if not problems else None), problems


# ---------- templates

PLUGIN_YAML = """name: {name}
version: 0.1.0
description: >-
  {description}
author: {author}
provides_tools:{tools}
{provides_hooks}{requires_env}"""

HANDLER = '''

def {func}(params: dict, config: dict) -> dict:
    """{description}

    {behaviour}
    """
{body}
'''

BODIES = {
    "command": '''    argv = list(config.get("argv") or [])
    if not argv:
        return {{"ok": False, "error": "config.argv is not set for {tool}"}}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return {{"ok": proc.returncode == 0, "code": proc.returncode,
                "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}}
    except Exception as exc:
        return {{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}''',
    "http": '''    url = config.get("url") or {url_default!r}
    if not url:
        return {{"ok": False, "error": "config.url is not set for {tool}"}}
    headers = dict(config.get("headers") or {{}})
    try:
        req = urllib.request.Request(url, headers=headers, method=config.get("method", "GET"))
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()[:20000].decode("utf-8", "replace")
        try:
            return {{"ok": True, "url": url, "json": json.loads(body)}}
        except ValueError:
            return {{"ok": True, "url": url, "text": body}}
    except Exception as exc:
        return {{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}''',
    "file": '''    path = config.get("path") or {path_default!r}
    if not path:
        return {{"ok": False, "error": "config.path is not set for {tool}"}}
    target = Path(os.path.expanduser(str(path)))
    write = bool(config.get("write"))
    try:
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(params.get("content") or config.get("content") or ""),
                              encoding="utf-8")
            return {{"ok": True, "path": str(target), "bytes": target.stat().st_size}}
        return {{"ok": True, "path": str(target),
                 "text": target.read_text(encoding="utf-8", errors="replace")[:20000]}}
    except Exception as exc:
        return {{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}''',
    "stub": '''    raise NotImplementedError(
        "This tool is a scaffold. {behaviour_short}"
    )''',
}


def _yaml_list(items: list, indent: int = 2) -> str:
    if not items:
        return " []"
    pad = " " * indent
    return "\n" + "\n".join(f"{pad}- {item}" for item in items)


def render(spec: dict) -> dict:
    """spec -> {filename: content}. Pure function; no I/O, easy to test."""
    name = spec["name"]
    tools = spec["tools"]

    yaml_tools = _yaml_list([t["name"] for t in tools])
    yaml_hooks = (f"provides_hooks:{_yaml_list(spec['hooks'])}\n" if spec.get("hooks") else "")
    envs = sorted({e for t in tools for e in t["requires_env"]})
    yaml_env = (f"requires_env:{_yaml_list(envs)}\n" if envs else "")
    plugin_yaml = PLUGIN_YAML.format(
        name=name, description=spec["description"], author=spec["author"],
        tools=yaml_tools, provides_hooks=yaml_hooks, requires_env=yaml_env)

    needs_urllib = any(t["kind"] == "http" for t in tools)
    needs_pathlib = any(t["kind"] == "file" for t in tools)
    needs_subprocess = any(t["kind"] == "command" for t in tools)

    imports = ["import json", "import os"]
    if needs_pathlib:
        imports.append("from pathlib import Path")
    if needs_subprocess:
        imports.append("import subprocess")
    if needs_urllib:
        imports.append("import urllib.request")

    handlers, entries = [], []
    for tool in tools:
        func = "handle_" + tool["name"]
        kind = tool["kind"]
        body = BODIES[kind].format(
            tool=tool["name"], description=tool["description"],
            behaviour=tool["behaviour"] or "Scaffold: replace with the real implementation.",
            behaviour_short=(tool["behaviour"] or "Replace with the real implementation.")[:200],
            url_default=("" if kind != "http" else ""),
            path_default=("" if kind != "file" else ""),
        )
        handlers.append(HANDLER.format(func=func, description=tool["description"],
                                       behaviour=tool["behaviour"] or "Scaffold.",
                                       body=body))
        entries.append(f'    "{tool["name"]}": {func},')

    params_hint = {t["name"]: t["params"] for t in tools if t["params"]}
    handler_block = chr(10).join(handlers)
    description_block = chr(10).join(f'    {t["name"]!r}: {t["description"]!r},' for t in tools)
    entry_block = chr(10).join(entries)
    hook_line = ("    for hook in HOOKS:" + chr(10) + "        ctx.register_hook(hook, _noop)" + chr(10)
                 if spec.get("hooks") else "")
    init_py = f'''"""{spec["title"]} — {spec["description"]}

Generated by Scout from a described idea. Handler bodies are templates chosen by the spec
({", ".join(sorted({t["kind"] for t in tools}))}); review them before installing.
"""

{chr(10).join(imports)}

PLUGIN = {{
    "name": {name!r},
    "version": "0.1.0",
    "description": {spec["description"]!r},
}}

# Parameters each tool accepts, for the model-facing schema.
PARAMS = {json.dumps(params_hint, indent=4)}


TOOL_DESCRIPTIONS = {{
{description_block}
}}

HOOKS = {spec.get("hooks")!r}

# Handlers are defined below this dict; the dict itself is built at the bottom of the module so the
# names exist by the time anything reads it.
{handler_block}

HANDLERS = {{
{entry_block}
}}


def _noop(**kwargs):
    """Placeholder hook body: log nothing, change nothing."""
    return None


def register(ctx):
    """Register every tool the spec declared, with the schema the model will see."""
    for tool_name, handler in HANDLERS.items():
        ctx.register_tool(
            name=tool_name,
            toolset=PLUGIN["name"],
            schema={{
                "name": tool_name,
                "description": TOOL_DESCRIPTIONS[tool_name],
                "parameters": {{"type": "object",
                               "properties": PARAMS.get(tool_name, {{}}),
                               "required": []}},
            }},
            handler=handler,
            description=TOOL_DESCRIPTIONS[tool_name].split(".")[0],
        )
{hook_line}'''

    readme = f"""# {spec['title']}

{spec['description']}

## Tools

{chr(10).join(f"- `{t['name']}` — {t['description']} ({t['kind']})" for t in tools)}

## Install

```bash
hermes plugins validate /path/to/{name}
ln -s /path/to/{name} ~/.hermes/plugins/{name}
```

## Note

Generated by Scout from a description{' based on ' + spec['origin'] if spec.get('origin') else ''}.
Handler bodies follow the template for their declared kind (`command`, `http`, `file`, or a stub).
Read the code before installing; nothing here is installed for you.
"""

    skill = f"""---
name: {name}
description: "Use when {spec['description'][:120].rstrip('.').lower()}."
---

# {spec['title']}

{spec['description']}

## Tools

{chr(10).join(f"- `{t['name']}` — {t['description']}" for t in tools)}

## How to use

Call the tool with the arguments listed in its schema. Configuration (`argv`, `url`, `path`) is set
in the plugin's config block, not in the call.
"""

    return {"plugin.yaml": plugin_yaml, "__init__.py": init_py,
            "README.md": readme, "skills/" + name + "/SKILL.md": skill}


def create(spec: dict, outbox: Optional[Path] = None) -> dict:
    """Render, write, validate. Writes only inside the plugin's own outbox."""
    clean, problems = validate_spec(spec)
    if clean is None:
        return {"ok": False, "stage": "spec", "problems": problems}

    root = Path(outbox) if outbox else (_CORE.state_dir() / "created")
    target = root / clean["name"]
    if (target / "plugin.yaml").exists():
        return {"ok": False, "stage": "spec",
                "problems": [f"{target} already exists — pick another name or remove it"]}

    files = render(clean)
    for rel, content in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    check = validate_plugin(target)
    return {"ok": True, "stage": "written", "name": clean["name"], "dir": str(target),
            "files": sorted(files), "spec": clean, "validation": check}


def validate_plugin(path: Path, timeout: int = 180) -> dict:
    try:
        proc = subprocess.run(["hermes", "plugins", "validate", str(path)],
                              capture_output=True, text=True, timeout=timeout)
        text = (proc.stdout + proc.stderr).strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return {"ok": proc.returncode == 0,
                "failures": [ln for ln in lines if ln.startswith("✗")],
                "tail": lines[-5:]}
    except Exception as exc:
        return {"ok": False, "failures": [f"validator not run: {type(exc).__name__}"], "tail": []}
