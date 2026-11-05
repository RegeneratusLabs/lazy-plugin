# pluginscout

You have an instrument that knows what you tried and could not do. Reach for it — but report,
never install.

## When to run it

Call `pluginscout_report` when the user asks any of these:

- "what's missing", "what should I install", "is there a plugin for X"
- "why do you keep working around this", "what are you bad at"
- "what's slowing you down", "what should I stop maintaining"
- after you just wrote a skill to work around a limitation — that event is itself recorded

Do not run it unprompted on every turn. It is a diagnostic, not a heartbeat.

## How to read it

- **matches**: a skill whose body invokes a concrete identifier (command, package, hostname, env
  var) that equals a catalog plugin's name, a tool it provides, or its repo name. Exact identity
  only — no prose guessing. Low counts are normal: most skills are workflow knowledge, not tool
  wrappers.
- **gaps**: recorded from real tool results (command-not-found, tool errors, repeated shell-outs)
  and from skills you created. These are facts, not inferences.

## Rules

1. **Never install.** Print `hermes plugins install <id>` and let the user run it. Installing is
   their consent to give a plugin code execution, not yours to take.
2. **Never edit or archive a skill** because of a match. A skill can legitimately be better than
   the plugin. Report, recommend, stop.
3. **Show evidence.** When you recommend a plugin, include the matched identifiers
   (`commands:brightdata`) from `pluginscout_explain`. If you can't name the evidence, don't make
   the claim.
4. **Don't dress it up.** "3 of 199 skills overlap a catalog plugin" is the honest sentence. Do not
   inflate a thin result into a headline.
