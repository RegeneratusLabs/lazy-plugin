---
name: lazy-plugin
description: "Use when the user wants a new plugin, or asks whether something they keep doing could be one."
---

# Lazy Plugin

Turns a description, an existing skill, or a cron job into a Hermes plugin that validates.

## When to use

- The user says "I wish Hermes could…", "make me a plugin that…", or "could this be a plugin?"
- A cron job keeps burning model calls on the same task every day.
- A skill has become mostly shell commands and would be better as tools.

## Tools

- `lazyplugin_sources` — what can be built from: agent-written skills and scheduled cron jobs.
- `lazyplugin_create` — build one. Pass `idea`, or `source_kind` + `source_name` to build from an
  existing skill or cron job.
- `lazyplugin_built` — what has already been generated, with paths.

## How to use it well

1. Call `lazyplugin_sources` first when the user is vague — the skill or cron job list is usually
   where the real idea is.
2. Call `lazyplugin_create` with a concrete sentence: what triggers it, what it reads or calls, and
   what it returns.
3. Read the returned `validation` block out loud. `ok: true` means it passed the same gate the
   catalog CI runs; anything else lists the exact ✗ lines.
4. Tell the user the outbox path. Never install it for them — the last step is theirs.

## What it will not do

- Write a hand-rolled implementation. Handler bodies come from four templates (`command`, `http`,
  `file`, `stub`); a `stub` tool documents the behaviour and raises until someone fills it in.
- Install, enable, or register the result.
- Guess: a spec that fails validation is refused before any file exists.
