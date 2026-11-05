# Lazy Plugin

**Describe a plugin, or point at something you already do — get a plugin that validates.**

```
┌─ Build a plugin ────────────────────────────────────────────────────┐
│ A plugin that watches GPU listings and tells me when one drops      │
│ under $600…                                                          │
│                                                                      │
│ or start from  [ a skill (43) ▾ ]  [ choose one… ▾ ]  [Build plugin] │
└──────────────────────────────────────────────────────────────────────┘
```

Three entry points, one engine:

| Start from | Why it works |
|---|---|
| **a description** | you know what you want; it becomes tools |
| **a skill the agent wrote** | the procedure is already written — it becomes tools instead of instructions |
| **a cron job you run** | recurring work with a schedule and a failure history — it becomes a plugin instead of a model call |

## How it builds

```
describe → [model] → spec: name, 1-5 tools, handler kind, params, hooks
         → [templates] → plugin.yaml + __init__.py + README.md + SKILL.md
         → [validator] → pass, or the exact ✗ lines
```

**The model writes the spec. Templates write the code.** Model-authored Python is how you get
plausible garbage that dies on import; model-authored *intent* rendered through fixed templates
always registers, always declares exactly the capabilities it provides, and cannot carry injected
code.

Handler bodies are limited to four shapes:

- `command` — runs a binary from `config.argv` (list argv, never a shell string)
- `http` — GET/POST `config.url` with headers, JSON parsed when possible
- `file` — read/write `config.path`
- `stub` — raises `NotImplementedError` carrying the described behaviour

A spec that cannot be built is refused **before** any file is written: name shape, description
length, 1–5 tools, unique snake_case names, bounded params, known hook names.

## Proof

Generated from a one-line description on this machine:

```
✓ manifest — plugin.yaml parses          ✓ loadable — entry: __init__.py
✓ capability probe                        ✓ security scan — safe
✓ built-in tool collisions — none         Validation passed.
```

Then imported and registered: 2 tools with correct model-facing schemas, 1 hook, handlers that
return `{"ok": false, "error": "config.url is not set"}` instead of raising.

## Never installs

Generated plugins land in `$HERMES_HOME/lazy-plugin/created/<name>/`. Nothing is symlinked into
`~/.hermes/plugins`, nothing is registered, nothing runs. You read the code, then decide:

```bash
hermes plugins validate $HERMES_HOME/lazy-plugin/created/gpu-price-watch
ln -s $HERMES_HOME/lazy-plugin/created/gpu-price-watch ~/.hermes/plugins/gpu-price-watch
```

## Tools

| Tool | Does |
|---|---|
| `lazyplugin_create` | build from `idea`, or from `source_kind` + `source_name` |
| `lazyplugin_sources` | list agent-written skills and cron jobs |
| `lazyplugin_built` | list what has been generated, with paths |

## Tests

```bash
python3 -m pytest tests -q     # 92 passed
```

## Why this is not a skill

A skill cannot call a model, render files, run `hermes plugins validate` as a subprocess, retry on
its output, or hold a native desktop page with two dropdowns and a build button. The generation
loop and the validator round-trip are the product.

MIT.
