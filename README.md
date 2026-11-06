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

## Which model builds the plugins

The user's own. The model call happens **inside a tool call, inside a turn** — `lazyplugin_create` is
an ordinary tool, so the host resolves whatever model and credential that profile has: API key,
OAuth proxy, cloud or local. The plugin holds no key, names no provider, and shells out to nothing.

That is also what makes it distributable. Install it on any profile and the agent already knows how
to build plugins; nothing to configure and nothing to leak.

The desktop page is UI, not the builder. When it cannot reach a turn it writes the request to
`$HERMES_HOME/lazy-plugin/requests/`, and `lazyplugin_pending` hands it to the agent on the next
message. A dashboard request has no turn, so the host will not resolve credentials there — the page
queues instead of pretending, which is the correct behaviour rather than a workaround.

## Publishing to the community

There is no upload endpoint and no self-serve registry. The catalog's rule 1 is a **human-merged
gate**: a PR adding `plugin-catalog/<name>.yaml` to `NousResearch/hermes-agent`, pinning a full
40-character commit SHA of a public repo. So publishing is four steps, each one checkable:

```
hermes plugins validate <bundle> --install-deps     the gate catalog CI runs
git repo at a commit                                the SHA is the release
plugin-catalog/<name>.yaml pinned to that SHA       every field the loader reads
gh pr create → NousResearch/hermes-agent            one file, reviewed by a maintainer
```

**Publish to community** in the page does all of it with your `gh` login: validates, commits,
creates the public repo, writes the entry from the real manifest, then offers **Open the catalog
PR** — a fork, a branch, one added file, and the PR body with the disclosures rule 13 asks for.

Verified on a real build: `RegeneratusLabs/chinese-marketplace-sourcing`, pinned at
`c83bb98e…`, entry `OK: 1 file(s) valid` against `scripts/validate_plugin_catalog.py`. Installable
anywhere with `hermes plugins install chinese-marketplace-sourcing` once merged.

The PR is yours to send. Nothing here merges, and a maintainer can decline it.

## Never installs by itself

Generated plugins land in `$HERMES_HOME/lazy-plugin/created/<name>/`. Nothing is symlinked into
`~/.hermes/plugins` until you ask for it:

**Install it** re-runs the validator and links the bundle into `~/.hermes/plugins/<name>`, then
tells you the enable step. It refuses an unvalidated package and refuses to clobber an existing
plugin, so a second click cannot quietly shadow something you already run.

```bash
hermes plugins validate $HERMES_HOME/lazy-plugin/created/gpu-price-watch
ln -s $HERMES_HOME/lazy-plugin/created/gpu-price-watch ~/.hermes/plugins/gpu-price-watch
hermes plugins enable gpu-price-watch
```

## Tools

| Tool | Does |
|---|---|
| `lazyplugin_create` | build from `idea`, or from `source_kind` + `source_name` |
| `lazyplugin_sources` | list agent-written skills and cron jobs |
| `lazyplugin_built` | list what has been generated, with paths |

## Tests

```bash
python3 -m pytest tests -q     # 106 passed
```

## Why this is not a skill

A skill cannot call a model, render files, run `hermes plugins validate` as a subprocess, retry on
its output, or hold a native desktop page with two dropdowns and a build button. The generation
loop and the validator round-trip are the product.

MIT.
