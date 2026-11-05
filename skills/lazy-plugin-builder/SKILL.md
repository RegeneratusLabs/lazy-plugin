---
name: lazy-plugin-builder
description: "Use when building or changing a Hermes plugin: spec, templates, validator, then publish."
---

# Building a plugin properly

You are the craftsperson the Lazy Plugin page dispatches to. Build a *plugin*, not a prompt, and
never claim it works without the validator saying so.

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

## What not to do

- Do not add a `requirements.txt` for something the stdlib already does.
- Do not write a self-updater: the pinned SHA is the trust model.
- Do not declare capabilities you do not register, or hide ones you do.
- Do not install or publish on the user's behalf without saying what you are about to run.
