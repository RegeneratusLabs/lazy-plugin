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
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"lazyplugin_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_CORE = _load("core", "core.py")

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
KINDS = ("command", "http", "file", "stub")

# A name made only of these says nothing about what the plugin touches: "find-me-me" instead of
# "ebay-kitty-litter". The request words belong in the description, not the slug.
_FILLER_WORDS = {"find", "get", "search", "show", "make", "build", "give", "me", "my", "a", "an",
                 "the", "please", "want", "i", "it", "for", "best", "some", "to"}
MAX_TOOLS = 5


def _clean(text: str, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def validate_spec(spec: dict) -> tuple[Optional[dict], list]:
    """Return (clean_spec, problems). A spec with problems is never rendered."""
    problems = []
    if not isinstance(spec, dict):
        return None, ["spec is not an object"]

    name = _clean(spec.get("name"), 40).lower().replace("_", "-")
    parts = [p for p in name.split("-") if p]
    while len(parts) > 1 and parts[0] in _FILLER_WORDS:
        parts.pop(0)
    if [p for p in parts if p not in _FILLER_WORDS]:
        name = "-".join(parts)
    if not NAME_RE.fullmatch(name or ""):
        problems.append(f"name {name!r} must be lowercase-hyphenated, 3-40 chars")
    elif not [p for p in name.split("-") if p not in _FILLER_WORDS]:
        problems.append("name must say what the plugin acts on (ebay-kitty-litter), "
                        "not just the request (find-me-me)")

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
        request_in = raw.get("request")
        request_in = request_in if isinstance(request_in, dict) else {}
        clean_request = {
            "url": _clean(request_in.get("url"), 300),
            "method": "POST" if str(request_in.get("method") or "GET").upper() == "POST" else "GET",
            "query": {_clean(k, 40): _clean(v, 120)
                      for k, v in list((request_in.get("query") or {}).items())[:12]},
            "defaults": {_clean(k, 40): _clean(v, 120)
                         for k, v in list((request_in.get("defaults") or {}).items())[:8]},
            "headers": {_clean(k, 40): _clean(v, 200)
                        for k, v in list((request_in.get("headers") or {}).items())[:8]},
            "limit_param": _clean(request_in.get("limit_param"), 30),
            "items_path": _clean(request_in.get("items_path"), 80),
            "fields": {_clean(k, 40): _clean(v, 80)
                       for k, v in list((request_in.get("fields") or {}).items())[:10]},
        }
        if kind == "http" and not clean_request["url"]:
            clean_request["url"] = _clean(raw.get("target"), 300)
        if kind == "http" and not clean_request["url"]:
            problems.append(f"{tool_name}: an http tool needs request.url — where does it fetch from?")
            continue
        if kind == "http" and "://" not in clean_request["url"]:
            problems.append(
                f"{tool_name}: request.url must be absolute, with a scheme "
                f"(https://{clean_request['url'].lstrip('/')}) — urllib refuses a bare host")
            continue
        if kind == "http" and not clean_request["items_path"] and not clean_request["fields"]:
            pass  # a whole-document read is legitimate; no projection is not an error
        # A command with no argv, or a file tool with no path, renders a handler that can only ever
        # answer "nothing is configured" — it validates, registers, and cannot work. Refuse the
        # spec here, where the model can still be asked for the target, instead of shipping it.
        target = _clean(raw.get("target") or "", 300)
        if kind == "command" and not target:
            problems.append(f"{tool_name}: a command tool needs target — the argv to run "
                            "(e.g. \"ffprobe -v error\")")
            continue
        if kind == "file" and not target and "path" not in clean_params:
            problems.append(f"{tool_name}: a file tool needs target, or a declared `path` parameter "
                            "the caller can fill — otherwise it can only answer \"no path is configured\"")
            continue
        tools.append({
            "name": tool_name,
            "description": _clean(raw.get("description"), 200) or tool_name,
            "kind": kind,
            "request": clean_request,
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

def {func}(params: dict, **kwargs: Any) -> str:
    {doc}
{body}
'''

BODIES = {
    "command": '''    argv = list({argv!r})
    if not argv:
        return json.dumps({{"ok": False, "error": "no command is configured for {tool}"}})
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return json.dumps({{"ok": proc.returncode == 0, "code": proc.returncode,
                           "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}})
    except Exception as exc:
        return json.dumps({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}})''',
    "http": '''    # A caller-supplied url wins over the baked default: the tool declared a `url` parameter,
    # so ignoring it makes the smoke test (and any caller) hit a URL nobody asked for.
    base = params.get("url") or {url!r}
    if base and "://" not in str(base):
        base = "https://" + str(base).lstrip("/")
    mapping = {query!r}
    defaults = {defaults!r}
    limit_param = {limit_param!r}
    items_path = {items_path!r}
    fields = {fields!r}
    method = {method!r}

    if not base:
        return json.dumps({{"ok": False, "error": "no request url is configured for {tool}"}})
    try:
        limit = int(params.get(limit_param or "limit") or defaults.get(limit_param or "limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))

    query = {{}}
    for key, token in mapping.items():
        value = token
        if isinstance(token, str) and token.startswith("$") and not token.startswith("$env:"):
            value = params.get(token[1:])
            if value in (None, ""):
                value = defaults.get(token[1:], "")
        if value in (None, ""):
            continue
        try:
            query[key] = _token(value)
        except ValueError as exc:
            return json.dumps({{"ok": False, "error": str(exc)}})

    url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(query) if query else base
    headers = {{"Accept": "application/json",
               "User-Agent": "hermes-plugin/1.0 (+https://hermes-agent.nousresearch.com)"}}
    for key, token in {headers!r}.items():
        try:
            headers[key] = _token(token)
        except ValueError as exc:
            return json.dumps({{"ok": False, "error": str(exc)}})
    try:
        request = urllib.request.Request(url, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()[:400000].decode("utf-8", "replace")
    except Exception as exc:
        return json.dumps({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}", "url": url}})

    try:
        payload = json.loads(raw)
    except ValueError:
        return json.dumps({{"ok": True, "url": url, "text": raw[:4000]}})

    items = payload
    for part in [p for p in items_path.split(".") if p]:
        if isinstance(items, dict):
            items = items.get(part)
        else:
            break
    if fields and isinstance(items, list):
        items = [{{label: _dig(row, path) for label, path in fields.items()}} for row in items[:limit]]
    elif isinstance(items, list):
        items = items[:limit]
    return json.dumps({{"ok": True, "url": url,
                       "count": len(items) if isinstance(items, list) else 1,
                       "items": items}}, ensure_ascii=False)''',
    "file": '''    path = params.get("path") or {path_default!r}
    if not path:
        return json.dumps({{"ok": False, "error": "no path is configured for {tool}"}})
    target = Path(os.path.expanduser(str(path)))
    try:
        if params.get("write"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(params.get("content") or ""), encoding="utf-8")
            return json.dumps({{"ok": True, "path": str(target), "bytes": target.stat().st_size}})
        return json.dumps({{"ok": True, "path": str(target),
                           "text": target.read_text(encoding="utf-8", errors="replace")[:20000]}},
                          ensure_ascii=False)
    except Exception as exc:
        return json.dumps({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}})''',
    "stub": '''    raise NotImplementedError({behaviour_message})''',
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
        imports.append("import re")
        imports.append("import urllib.parse")
        imports.append("import urllib.request")
    imports.append("from typing import Any")

    handlers, entries = [], []
    for tool in tools:
        func = "handle_" + tool["name"]
        kind = tool["kind"]
        request = tool.get("request") or {}
        body = BODIES[kind].format(
            tool=tool["name"], description=tool["description"],
            behaviour=tool["behaviour"] or "Scaffold: replace with the real implementation.",
            behaviour_message=repr("This tool is a scaffold. "
                                   + (tool["behaviour"] or "Replace with the real implementation.")[:200]),
            url_default=("" if kind != "http" else ""),
            path_default=(tool.get("target") or ""),
            argv=[p for p in str(tool.get("target") or "").split()][:8],
            url=request.get("url", ""),
            query=request.get("query") or {},
            defaults=request.get("defaults") or {},
            limit_param=request.get("limit_param") or "",
            items_path=request.get("items_path") or "",
            fields=request.get("fields") or {},
            method=request.get("method") or "GET",
            headers=request.get("headers") or {},
        )
        doc = f"{tool['description']}\n\n{tool['behaviour'] or 'Scaffold.'}"
        handlers.append(HANDLER.format(func=func, doc=repr(doc), body=body))
        entries.append(f'    "{tool["name"]}": {func},')

    dig_helper = chr(10).join([
        "",
        "",
        "def _dig(obj, path):",
        "    # Follow a dotted path through dicts and lists; None when the path is not there.",
        "    for part in [p for p in str(path or \"\").split(\".\") if p]:",
        "        if isinstance(obj, dict):",
        "            obj = obj.get(part)",
        "        elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):",
        "            obj = obj[int(part)]",
        "        else:",
        "            return None",
        "    return obj",
        "",
        "",
        "def _token(value):",
        "    # Replace $env:NAME anywhere in a value; a missing variable is a named error, not a 401.",
        "    def sub(match):",
        "        name = match.group(1)",
        "        found = os.environ.get(name)",
        "        if not found:",
        "            raise ValueError(name + \" is not set — put it in ~/.hermes/.env\")",
        "        return str(found)",
        "    return re.sub(r'\\$env:([A-Za-z_][A-Za-z0-9_]*)', sub, str(value))",
    ]) if needs_urllib else ""
    params_hint = {t["name"]: t["params"] for t in tools if t["params"]}
    handler_block = chr(10).join(handlers)
    description_block = chr(10).join(f'    {t["name"]!r}: {t["description"]!r},' for t in tools)
    entry_block = chr(10).join(entries)
    hook_line = ("    for hook in HOOKS:" + chr(10) + "        ctx.register_hook(hook, _noop)" + chr(10)
                 if spec.get("hooks") else "")
    init_py = f'''"""{spec["title"]} — {spec["description"]}

Generated by Lazy Plugin from a described idea. Handler bodies are templates chosen by the spec
({", ".join(sorted({t["kind"] for t in tools}))}); review them before installing.
"""

{chr(10).join(imports)}
{dig_helper}

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

Generated by Lazy Plugin from a description{' based on ' + spec['origin'] if spec.get('origin') else ''}.
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


# ---------- the model writes the spec, templates write the code

SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string"},
        "hooks": {"type": "array", "items": {"type": "string"}},
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "behaviour": {"type": "string"},
                    "params": {"type": "object"},
                    "requires_env": {"type": "array", "items": {"type": "string"}},
                    "target": {"type": "string"},
                    "request": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "method": {"type": "string", "enum": ["GET", "POST"]},
                            "query": {"type": "object"},
                            "defaults": {"type": "object"},
                            "headers": {"type": "object"},
                            "limit_param": {"type": "string"},
                            "items_path": {"type": "string"},
                            "fields": {"type": "object"},
                        },
                    },
                },
                "required": ["name", "description", "kind"],
            },
        },
    },
    "required": ["name", "description", "tools"],
}

DRAFT_INSTRUCTIONS = """You design Hermes plugins from a description or from an existing workflow.

Return ONE JSON object with this shape:
{"name": "lowercase-hyphenated", "title": "Human Title", "description": "one or two sentences",
 "category": "tools", "hooks": ["on_session_end"], "tools": [
   {"name": "snake_case_tool", "description": "what it does, for the model",
    "kind": "command|http|file|stub", "behaviour": "precise implementation note",
    "params": {"arg": "what it means"}, "requires_env": ["API_KEY"]}]}

Rules that decide whether this plugin is usable:
- 1 to 5 tools. Each tool does one job.
- kind=command when the job runs a binary (argv from config, never a shell string).
- kind=http when the job fetches or posts a URL, and then `request` is the whole point:
  {"request": {"url": "https://api.example.com/v1/search",
               "query": {"q": "$query", "key": "$env:EXAMPLE_API_KEY", "limit": "$limit"},
               "defaults": {"query": "what the user asked for", "limit": "10"},
               "headers": {"Authorization": "Bearer $env:EXAMPLE_API_KEY"},
               "limit_param": "limit",
               "items_path": "results",
               "fields": {"title": "name", "url": "links.self", "price": "price.value"}}}
  `$name` reads that tool parameter (falling back to `defaults`); `$env:NAME` reads an env var and
  must also be listed in requires_env; `items_path` is the dotted path to the result list;
  `fields` maps your output label to the dotted path inside each result. An http tool with no
  request.url is refused, because a tool that fetches nothing is not a plugin.
- "target" is a shorthand for request.url when there is exactly one.
- kind=file when the job reads or writes a path.
- kind=stub ONLY when the job needs real logic that templates cannot express; then `behaviour`
  must describe exactly what a developer should write.
- requires_env lists env vars the tool needs, or omit it.
- No prose outside the JSON. No code fences."""


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    for candidate in (text, text.split("```json", 1)[-1].split("```", 1)[0] if "```" in text else text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
    start, depth = None, 0
    for index, char in enumerate(text):
        if char == "{":
            start = index if start is None else start
            depth += 1
        elif char == "}" and start is not None:
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:index + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except ValueError:
                    start = None
    return None


def source_context(core, kind: str, name: str) -> str:
    """The selected skill or cron job, as text the model has to build from."""
    if not kind or not name:
        return ""
    if kind == "skill":
        for skill in core.scan_skills():
            if skill.get("name") == name:
                try:
                    body = Path(skill["path"]).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    return ""
                return f"SKILL {name}\n\n{body[:6000]}"
        return ""
    if kind == "cron":
        try:
            raw = json.loads((core.hermes_home() / "cron" / "jobs.json").read_text(encoding="utf-8"))
            raw = raw if isinstance(raw, list) else raw.get("jobs", [])
            for job in raw:
                if name in (job.get("name"), job.get("id")):
                    schedule = job.get("schedule") or {}
                    return (f"CRON JOB {job.get('name')}\n"
                            f"schedule: {schedule.get('expr') or schedule.get('value') or 'unknown'}\n"
                            f"deliver: {job.get('deliver') or 'default'}\n\n"
                            f"{(job.get('prompt') or '')[:6000]}")
        except Exception:
            return ""
    return ""


def draft_spec(idea: str, llm, context: str = "") -> dict:
    """Ask the model for a spec, then hold it to the same rules as a hand-written one."""
    idea = _clean(idea, 2000)
    if len(idea) < 10:
        return {"ok": False, "stage": "input", "problems": ["describe the plugin in a sentence or two"]}
    if llm is None:
        return {"ok": False, "stage": "llm",
                "problems": ["no model available in this process — the page can still list sources"]}

    payload = idea if not context else f"{idea}\n\nContext from the user's own setup:\n{context[:6000]}"
    meta = {"lane": None, "model": None, "tokens": None}
    raw = ""
    attempt_at = time.time()
    try:
        result = llm.complete_structured(
            instructions=DRAFT_INSTRUCTIONS,
            input=[{"type": "text", "text": payload}],
            json_schema=SPEC_SCHEMA,
            schema_name="scout.plugin_spec",
            purpose="lazy-plugin.create",
            temperature=0.2,
            max_tokens=2000,
            timeout=180,
        )
        raw = getattr(result, "text", "") or ""
        parsed = getattr(result, "parsed", None) or _extract_json(raw)
        meta.update(lane="structured", model=getattr(result, "model", None),
                    tokens=getattr(getattr(result, "usage", None), "total_tokens", None),
                    seconds=round(time.time() - attempt_at, 2))
    except Exception as first:
        # How long the structured lane burned before failing is the difference between a 20-second
        # build and a three-minute one, so it is recorded rather than swallowed.
        meta["structured_error"] = f"{type(first).__name__}: {first}"[:300]
        meta["structured_seconds"] = round(time.time() - attempt_at, 2)
        attempt_at = time.time()
        try:
            result = llm.complete(
                messages=[{"role": "system",
                           "content": DRAFT_INSTRUCTIONS + "\n\nJSON only, no code fence."},
                          {"role": "user", "content": payload}],
                temperature=0.2, max_tokens=2000, timeout=180,
                purpose="lazy-plugin.create.chat",
            )
            raw = getattr(result, "text", "") or ""
            parsed = _extract_json(raw)
            meta.update(lane="chat", model=getattr(result, "model", None),
                        tokens=getattr(getattr(result, "usage", None), "total_tokens", None),
                        seconds=round(time.time() - attempt_at, 2))
        except Exception as second:
            return {"ok": False, "stage": "llm",
                    "problems": [f"model call failed: {type(second).__name__}: {second}"[:300]]}

    if not isinstance(parsed, dict):
        return {"ok": False, "stage": "parse", "raw": raw[:800], "meta": meta,
                "problems": ["the model did not return a JSON object"]}

    clean, problems = validate_spec(parsed)
    if clean is None and problems:
        # One repair pass, then stop. The refusal lines are the most useful prompt we will ever have
        # for this spec, and handing them back is far cheaper than a user hitting a dead end.
        repaired, repair_problems = _repair_spec(llm, payload, problems, meta)
        if repaired is not None:
            clean, problems = repaired, []
        else:
            problems = repair_problems or problems
    return {"ok": clean is not None, "stage": "spec" if clean is None else "drafted",
            "spec": clean, "problems": problems, "raw": raw[:800], "meta": meta}


def _repair_spec(llm, payload: str, problems: list, meta: dict):
    """Hand the refusal back once. Returns (clean_spec, None) or (None, new_problems)."""
    asked = (f"{payload}\n\nYour spec was refused for these reasons:\n- "
             + "\n- ".join(str(problem) for problem in problems[:8])
             + "\n\nReturn ONE corrected JSON object of the same shape, fixing exactly those. "
               "Do not add tools that were not asked for.")
    try:
        result = llm.complete(
            messages=[{"role": "system", "content": DRAFT_INSTRUCTIONS + "\n\nJSON only, no code fence."},
                      {"role": "user", "content": asked}],
            temperature=0.1, max_tokens=2000, timeout=180,
            purpose="lazy-plugin.create.repair",
        )
    except Exception as exc:
        meta["repair_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return None, None
    parsed = _extract_json(getattr(result, "text", "") or "")
    if not isinstance(parsed, dict):
        meta["repair_error"] = "the repair attempt did not return a JSON object"
        return None, None
    clean, remaining = validate_spec(parsed)
    meta["repaired"] = {"asked": [str(problem)[:120] for problem in problems[:8]],
                        "fixed": clean is not None}
    if clean is None:
        meta["repaired"]["still_refused"] = [str(problem)[:120] for problem in remaining[:8]]
    return clean, remaining


def read_manifest(bundle: Path) -> dict:
    """plugin.yaml -> dict, with a list-aware fallback so it works without PyYAML."""
    path = Path(bundle) / "plugin.yaml"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    out, pending = {}, None
    for line in text.splitlines():
        item = re.match(r"^\s+-\s*(.+)$", line)
        if item and pending:
            out[pending].append(item.group(1).strip().strip("'\""))
            continue
        key = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if not key:
            pending = None
            continue
        field, value = key.group(1), key.group(2).strip()
        if value:
            out[field] = value.strip("'\"")
            pending = None
        else:
            out[field] = []
            pending = field
    return out


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

    # The official handler contract is a gate, not advice: one positional (params), **kwargs, a JSON
    # string back. A bundle that misses it is deleted rather than left on the shelf looking fine.
    violations = _smoke_mod().contract_violations(target)
    if violations:
        import shutil as _shutil
        _shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "stage": "contract", "problems": violations,
                "error": "the generated code does not meet the Hermes plugin contract: "
                         + "; ".join(violations[:3])}

    # Structure is not behaviour: load it and call every tool once. A build that cannot run is
    # reported as such now, not discovered later by whoever installs it.
    report = smoke_plugin(target)
    # Seed the page's validation cache with what this build already proved, so the first tile
    # fetch doesn't pay the validator subprocess (~2.6 s) all over again.
    _remember_validation(target, check)
    return {"ok": True, "stage": "checked", "name": clean["name"], "dir": str(target),
            "files": sorted(files), "spec": clean, "validation": check,
            "smoke": report, "works": report.get("verdict") == "works",
            "headline": _smoke_headline(report)}


def _remember_validation(target: Path, check: dict) -> None:
    """Write the same {name: {mtime, ok, tail}} row dashboard.plugin_api._created caches, so a
    bundle this process just validated is not validated again by the page's next fetch."""
    try:
        path = _CORE.state_dir() / "validation.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        modified = max((item.stat().st_mtime for item in target.rglob("*") if item.is_file()),
                       default=0)
        data[target.name] = {"mtime": modified, "ok": bool(check.get("ok")),
                             "tail": [line for line in (check.get("tail") or []) if line.strip()][-3:]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _smoke_mod():
    spec = importlib.util.spec_from_file_location(
        "lazyplugin_smoke_creator", Path(__file__).resolve().parent / "smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def smoke_plugin(path: Path, live: bool = True) -> dict:
    """Run the smoke test and keep the report beside the bundle, so a tile can show it."""
    try:
        module = _smoke_mod()
        report = module.smoke(path, live=live)
        module.write_report(path, report)
        return report
    except Exception as exc:
        return {"plugin": Path(path).name, "verdict": "unchecked", "tools": [],
                "notes": [f"smoke test could not run: {type(exc).__name__}: {exc}"]}


def _smoke_headline(report: dict) -> str:
    try:
        return _smoke_mod().headline(report)
    except Exception:
        return "not checked"


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
