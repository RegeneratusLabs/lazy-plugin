# pluginscout

**Your skill library is plugin debt — mostly it isn't, and this tells you which parts are.**

Hermes records what your agent did. Nothing records what it *couldn't* do. `pluginscout` reads two
things nobody joins up: the identifiers your skills actually invoke, and the failures your tool
calls actually produced. Then it puts a catalog plugin next to each one that already exists.

Read-only. No LLM in the matching path. Never installs anything.

```
25 capability gaps from real tool calls (57 occurrences, 25 mined from transcripts)

  gap pkg:pandas               ×9   cmd_not_found   backfill
  gap pkg:markdown             ×7   cmd_not_found   backfill
  gap pkg:weasyprint           ×5   cmd_not_found   backfill
  gap cmd:pandoc               ×3   cmd_not_found   backfill
  gap pkg:youtube_transcript_api ×3 cmd_not_found   backfill

4 of 199 skills also overlap a catalog plugin (1204 lines, 3 not installed)

  oauth-local-server-flow  -> tidal          hosts:tidal
  ethics-filter            -> ethics-filter  commands:ethics-filter  [installed]
  hermes-band              -> hermes-band    commands:hermes-band
  spotify                  -> spotify        hosts:spotify
```

That output is real, from a 199-skill profile against the live 976-entry catalog, with 99 session
transcripts (4,892 tool calls) mined in 1.7 seconds.

## Why this isn't a skill

The hackathon favours entries that "do more than a prompt or a skill could." Three things here are
outside what a skill can do, and they are the reason the plugin exists:

1. **It watches without being asked.** `post_tool_call` fires on every tool call whether or not any
   skill is loaded. A skill only exists while it's in context; it cannot observe the failure that
   happens three turns after it was read.
2. **It remembers.** The ledger is SQLite on disk, keyed by signature, aggregated across sessions.
   A skill has no storage — the model would have to re-derive every prior failure from context it
   no longer has.
3. **It reads history a skill can't afford to.** `pluginscout_backfill` walks 32 MB of JSONL
   transcripts, keeps only missing-binary and missing-package events, and does it in under two
   seconds. Loading that into a context window is not a thing that can happen.

The skill↔catalog ledger, on its own, *is* reproducible with a script and a prompt — which is why
it's the second panel in the UI and not the headline any more.

## Why the number is small

An earlier version of this plugin matched on words. Scored against the same 199 skills it reported
**199 of 199** matches — `cron` appearing 40 times in a skill "matched" a cron plugin, `access` and
`changes` matched a finance plugin. It was useless and it looked impressive, which is the worst
combination.

`pluginscout` matches only on **concrete identifiers**: a command head in a fenced block, a package
name from an install line, a hostname in a URL, an env var ending `_API_KEY`/`_TOKEN`/`_SECRET`.
It matches those against three things only — a plugin's name, a tool it declares in
`provides_tools`, or its repo name. A skill called `ethics-filter` does **not** match the
`ethics-filter` plugin unless the skill's body actually invokes it. That is why the honest number is
4 and not 199, and why 4 is the more interesting number.

## Install

```bash
hermes plugins install <owner>/pluginscout
```

Until it's in the catalog, symlink a checkout:

```bash
ln -s "$PWD" ~/.hermes/plugins/pluginscout
hermes plugins doctor pluginscout      # expect: 3 tool(s), 3 hook(s)
```

Tools land in the next session (plugin tools are deferred behind the frozen prompt prefix). The
dashboard tab appears immediately after a dashboard refresh.

## What you get

Three tools:

| Tool | What it answers |
|---|---|
| `pluginscout_report` | Which skills overlap a catalog plugin, plus recorded gaps. `summary` \| `full` \| `json` |
| `pluginscout_refresh` | Re-fetch the catalog and rebuild the index (one GET, cached 24h) |
| `pluginscout_explain` | The exact evidence behind one match or one gap — so it can't bluff |

Three hooks:

- `post_tool_call` — records `cmd_not_found`, `tool_error`, and `repeated_shellout` (the same
  command head three times in a session)
- `on_skill_lifecycle` — records `skill_created`: a skill the agent wrote to cope is itself a gap
- `on_session_end` — flushes the buffer, prunes to 30 days / 5000 rows

A **Scout** dashboard tab: the debt meter, the skill→plugin ledger with copyable install commands,
the gap feed, and catalog freshness.

A CLI that works without the model in the loop:

```bash
python3 cli.py report            # or: hermes pluginscout report, when plugin isolation is in_process
python3 cli.py gaps
python3 cli.py explain spotify
python3 cli.py refresh
```

## Prior art

`github.com/smfworks/hermes-lofoten-challenge` → `team-stockfish/hermes-plugin-skill-gap-analyzer`
(a prior hackathon entry, not in the catalog) also analyses a skill library. It finds thin
categories, narrow skills and duplicate skills, and recommends **where to write more skills**. It
does not know the plugin catalog exists.

`pluginscout` answers the opposite question: **which skills a plugin has already made redundant,**
with the exact identifier as evidence and a pinned catalog entry as the output. Different input
signal, inverted output, and a runtime half (measured tool failures) that a static scan cannot have.
Also adjacent, also different: `token-lens` (token cost), `jev-skill-router-mcp` (which skill to
load), `mcp-plugin-creator` (make a plugin from an MCP server).

## Design rules (do not trade these away)

1. **Never install.** It prints the command. Installation is consent to code execution.
2. **Never edit, archive or delete a skill.** The curator owns that; a match is not proof.
3. **No LLM in the matching path.** If an identifier can't be named, no match is reported.
4. **Report the small number honestly.** A thin result is the result.
5. **Never break a turn.** Every hook body is wrapped; a diagnostic that raises is a bug.

## Limits

- Recall is deliberately low. A skill that *describes* scraping without naming `brightdata` will not
  match the `brightdata` plugin. That's a feature, not a gap to "fix" with fuzzy matching.
- Host matching can fire on a single URL mention. Known and accepted; `explain` shows the evidence
  so you can judge it in one glance.
- The catalog index only knows name, `provides_tools`, and repo name. A plugin whose name has
  nothing to do with what it does will never be suggested.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install pytest && .venv/bin/python -m pytest tests -q
# 25 passed
```

The matcher tests exist mostly as tripwires: `test_prose_about_cron_does_not_match_cron_plugin` and
`test_skill_name_alone_does_not_match` are the two regressions that would quietly return this
plugin to the useless version.

## Credits

Built against the Hermes Agent plugin SDK (`NousResearch/hermes-agent`) — catalog API
`docs/api/plugin-catalog.json`, dashboard plugin contract, `ctx.register_tool` / `register_hook` /
`register_cli_command` / `register_skill`. The dashboard plugin pattern follows the
`hermes-achievements` and `kanban` tabs shipped with Hermes.

MIT.
