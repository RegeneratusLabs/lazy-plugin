# lazy-plugin — the product we are shipping

**A plugin that builds plugins, then proves they run.**

The one thing this does that nothing else in the catalog does: it dispatches a freshly generated
plugin's tools inside the host and grades the result. A scaffolder stops at `plugin.yaml`; a skill
stops at instructions. This ends with a verdict you can read before you install anything.

This document is the spec of record. `README.md` is the pitch; `DESIGN.md` is the page's visual
language. Anything not described here is not in the product.

## The loop

```
page (desktop)                 chat turn                    tool call
─────────────                  ─────────                    ─────────
"Give the cat a job"
  ↓ prompt.submit
                          agent reads the skill, drafts
                          a spec in words
                                    ↓ lazyplugin_create
                                                        validate_spec → templates → files
                                                        hermes plugins validate
                                                        dispatch every tool → verdict
                                    ↓
                          agent reports name + check + try-out
  ↓ new bundle appears
page dispatches it again itself
  ↓
receipt: plan · files · check · try-out   →  install / publish
```

Two properties hold the design together:

1. **The model authors intent, never code.** It returns a spec: a name, 1–3 tools, and for each tool
   what it reads or fetches, what it returns, whether it needs a key. Fixed templates render that
   into `plugin.yaml`, `__init__.py`, `README.md` and a skill. Generated code therefore always
   registers, always declares what it provides, and cannot carry injected logic.
2. **The page does not trust the agent's word.** When a bundle appears, the page calls
   `/created/smoke` itself and renders the verdict. A bundle that arrived with no dispatch report is
   labelled as hand-written, with the page's dispatch as its only gate.

## Handler shapes

| Shape | Body | Refused when |
|---|---|---|
| `command` | `subprocess.run` on a list argv from the spec's target | no target (what would it run?) |
| `http` | `urlopen` of a request URL, query built from declared params | no URL, or a bare host with no scheme |
| `file` | read/write a path, from the spec's target or a `path` argument | neither a target nor a declared `path` |
| `stub` | raises `NotImplementedError` carrying the described behaviour | — (a stub is honest, and grades `half-built`) |

A declared `url` or `path` argument always overrides the value baked into the spec, because a caller
that passes one means it.

## The gate order

Nothing is written until the spec passes; nothing is offered for install until it runs.

1. `validate_spec` — name, description length, 1–3 tools, unique snake_case tool names, real targets.
2. `render` — pure function, spec to files. No I/O.
3. `hermes plugins validate` — the catalog gate as a subprocess, its exact output kept.
4. `contract_violations` — one positional `params`, `**kwargs`, a `json.dumps` return. A bundle that
   misses the handler contract is deleted rather than left on the shelf looking fine.
5. `dispatch` — every tool called once through the real registry with sample arguments.
6. `similar_plugins` — the finished plugin against the live catalog, twice: on the idea before a
   build (a collision turns `make it` into a two-click verb) and on the receipt before publish
   (`similar`/`duplicate` turns `publish` into a two-click verb). Anchored on tool names and rare
   name tokens only; prose overlap can nudge a score but never qualify a match.

## Verdict vocabulary

| Verdict | Pill | What it means |
|---|---|---|
| `works` | purrs | called, returned real results |
| `needs-key` | needs a key | sound package, missing an env var |
| `upstream` | blocked upstream | our side works; the far end refused |
| `scaffold` | half-built | the handler was never written |
| `broken` | broken | would not load, or the handler raised |
| `unchecked` | not tried out | no dispatch on record |

The sentence under the pill always carries the fact — a status code, an exception line, or the tool
that failed. Colour is a hint; the sentence is the evidence.

## What it writes

```
$HERMES_HOME/lazy-plugin/
  created/<name>/     plugin.yaml, __init__.py, README.md, skills/<name>/SKILL.md, smoke.json
  validation.json     per-bundle {mtime, ok, tail}, so the page does not re-validate on every fetch
```

Nothing is linked into `~/.hermes/plugins` until **install** is clicked, which re-validates first and
refuses to clobber an existing plugin.

## Publishing

The catalog is a human-merged gate: a PR adds `plugin-catalog/<name>.yaml` to
`NousResearch/hermes-agent`, pinning a 40-character commit SHA of a public repo. **Publish** does the
mechanical half with the user's own `gh` login — validate, commit, create the repo, pin the SHA, write
the entry from the real manifest, open the PR. It never merges, and it never invents a capability the
manifest does not declare.

## Non-goals

- **A capability-gap finder.** It was built and measured: of 108 recorded gaps, one was
  catalog-answerable, and the top entries were `pip install` problems rather than plugin problems.
  Matching prose against a catalog is the hard part and it was not good enough to be worth the
  screen, so the hooks, the ledger and the matcher are gone. What is left is the loop above.
- **A registry.** There is no upload endpoint; the catalog PR is the distribution mechanism.
- **Installing for you.** Generation is not consent to run code.

## Tests

```bash
.venv/bin/python -m pytest tests -q     # 133 passed
hermes plugins validate .               # manifest, capabilities, security scan, no core override
```

The tripwires worth keeping: a spec with a dead target is refused rather than shipped, a handler that
needs a `config` argument is refused, and a bundle that validates but cannot dispatch is graded
`broken` instead of passing quietly.

## Credits

Built against the Hermes Agent plugin SDK — `ctx.register_tool`, the desktop plugin contract
(`@hermes/plugin-sdk`), and the catalog rules in `NousResearch/hermes-agent`. MIT.
