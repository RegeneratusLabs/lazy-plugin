---
name: lazy-plugin-builder
description: "Use when building or changing a Hermes plugin: spec, templates, validator, then publish."
---

# Building a plugin properly

You are the craftsperson the Lazy Plugin page dispatches to. Build a *plugin*, not a prompt, and
never claim it works without the validator saying so.

## First, check the queue

A build from the page usually arrives here as a turn, so the description is the user message you
already have. Only when the surface has no chat to hand a turn to (a browser tab, a phone) does the
page fall back to writing the request into `$HERMES_HOME/lazy-plugin/requests/` — if the user says
they queued one, call `lazyplugin_pending` first and build what is listed. When a request names no
URL, path or command, ask that one question instead of building a tool that does nothing.

The page dispatches whatever lands itself, so do not claim success on your own word: end with the
name, the validate line and the dispatch line, and let the verdict speak.

## The loop

1. **Spec first, in words.** Name, 1–5 tools, for each tool: what it does, what it reads or fetches,
   what it returns, and whether it needs a key. Show the spec to the user before writing files if
   anything is ambiguous.
2. **Render, don't freehand.** Handler bodies come from four shapes only:
   - `command` — argv list from `config.argv`, never a shell string
   - `http` — `urlopen` of `config.url`, JSON parsed when possible
   - `file` — pathlib read/write of `config.path`
   - `stub` — raises `NotImplementedError` carrying the described behaviour
   The model writes the *spec*; the templates write the code. Hand-written Python for the body is
   how a plugin reaches the user broken.
3. **Validate, always.**
   ```bash
   hermes plugins validate <bundle> --install-deps
   ```
   `✗` means fix it before going further. Never leave a bundle in a state the validator rejects.
4. **Then** install (`hermes plugins enable <name>`) or publish (repo → SHA pin → catalog entry).

## Where bundles live

```
$HERMES_HOME/lazy-plugin/created/<name>/
  plugin.yaml            manifest: name, version, description, provides_tools, provides_hooks
  __init__.py            register(ctx): ctx.register_tool(name, toolset, schema, handler)
  README.md              what it does, how to install
  skills/<name>/SKILL.md when the plugin should also teach the agent
```

## Editing an existing bundle

Read the file before changing it. Keep the manifest and the registration in step — a tool declared
in `plugin.yaml` that `__init__.py` does not register fails capability matching (catalog rule 6).
After any edit: re-run the validator, then `git -C <bundle> commit` so the next publish pins the
change.

## Template traps that validate but don't run

The generated bodies are stubs keyed to params the spec rarely declares. Read `__init__.py`
before reporting a build, and check these every time:

- **`file` tools must declare a param named literally `path`** (or a fixed `target`). Otherwise the
  spec is refused at the spec stage, before the validator even runs.
- **The `file` template writes only when passed `write` and `content`.** Neither is a declared
  param, so a freshly generated tool silently falls through to *reading* the target and dies with
  `FileNotFoundError`. Rewrite the body to use the params you actually declared.
- **The `http` template hardcodes the URL as a literal** (`base = '$site_url'`) and leaves `mapping`
  empty, so no caller param ever reaches the request. Build the URL from params.
- **`smoke.py` samples params by exact name.** `url` → `https://example.com`, `path` →
  `~/smoke.txt`, `query`/`q`/`text` → `cat`; anything unrecognised gets the junk string `test`.
  Name a fetch param `url` (keep a descriptive alias) or the smoke run always reports broken.
- **`ok:false` is classified `broken`**, not a warning. A handler that refuses a junk input the
  smoke host invented fails the gate — validate only what you can genuinely check, write the rest
  verbatim with a `warning` field.

`hermes plugins validate` passing does not mean the tools work: it checks the spec, the manifest and
registration, not behaviour. The smoke verdict is the real signal — re-run it from the repo with
`python3 -c "import smoke; smoke.smoke(Path(bundle))"`.

## What not to do

- Do not add a `requirements.txt` for something the stdlib already does.
- Do not write a self-updater: the pinned SHA is the trust model.
- Do not declare capabilities you do not register, or hide ones you do.
- Do not install or publish on the user's behalf without saying what you are about to run.
