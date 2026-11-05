# Scout

**Turns the skills your agent already wrote into validated Hermes marketplace packages.**

Your agent writes skills constantly — workarounds, procedures, hard-won fixes. They pile up in
`~/.hermes/skills/` and almost never leave your machine. Scout reads them, decides which are worth
publishing, proves what is private before anything is shared, and generates a submission bundle
that **passes the same `hermes plugins validate` gate the catalog CI runs**.

```
$ hermes pluginscout contributions --days 60

35 agent-written skills · 18 publishable · 12 need scrubbing · 5 keep private
```

## What it does

| Step | How | Why it is checkable |
|---|---|---|
| Find the agent's own skills | `agent_created` flag + `.usage.json` creation dates | you can list them yourself |
| Screen for privacy | every personal path, host, name, org, account, port — with line numbers | the evidence is on screen |
| Decide what can ship | step count, description, catalog collision | deterministic rules, no model call |
| Build the package | `plugin.json` + `skills/<slug>/SKILL.md` + `plugin-catalog/<slug>.yaml` + `SUBMISSION.md` | Agent Plugins v1 shape |
| **Validate it** | runs `hermes plugins validate` on the artifact and shows the output | the validator decides, not me |

Real run, 60 days, 976-plugin catalog:

```
30 prepared · 28 passed validate · 2 blocked · 5 keep private
```

The two blocked ones were blocked for good reason — the security scan caught `curl | python` and
`sudo` usage with line numbers. You see that before you open a PR, not after review.

## Verdicts

- **publish** — real steps, a description, no personal strings.
- **needs scrub** — good procedure, some of your environment in it. Packaging replaces those
  strings with `<path>`, `<host>`, `<name>`, `<port>` and records every redaction.
- **already covered** — a catalog plugin already ships it.
- **too thin** — fewer than three steps; not worth a stranger's time.
- **keep private** — too much of your setup is baked in. **Refused**, not published with a warning.

Skills whose bodies need the turn loop, a schedule or a UI are flagged **as plugin**, because
shipping a plugin-shaped thing as a skill is how you publish something broken.

## Install

```bash
ln -s /path/to/pluginscout ~/.hermes/plugins/pluginscout
hermes plugins validate ~/.hermes/plugins/pluginscout
hermes plugins doctor pluginscout
```

The page appears in the desktop app sidebar as **Scout**, after Skills.

## The bundle

```
outbox/project-handover-briefs/
├── plugin.json                        # Agent Plugins v1 (exact $schema)
├── skills/project-handover-briefs/SKILL.md       # scrubbed copy
├── plugin-catalog/project-handover-briefs.yaml   # the entry the PR expects, 40-char SHA pin
├── SUBMISSION.md              # fork / validate / PR steps, with this run's validator output
├── README.md                  # install + author credit, MIT
└── CONTRIBUTION.json          # every redaction, every transformation
```

`Prepare all` does this for every candidate in one pass and reports the validation tally.

What it deliberately does **not** do: push anything. The catalog is human-merged (rule 5: owner or
major-contributor submissions), so the last step is a PR you own. Scout gets you to a validated
package and a filled catalog entry.

## Why this is not a skill

A skill cannot read 30 bundles' worth of session history, run a subprocess validator per package,
write a plugin manifest, or hold a native desktop page. The hooks, the filesystem work, the
validator round-trip and the page are all outside what a `SKILL.md` can reach.

## What was cut, and why

The first half of this plugin was a plugin *recommender*: read your last week, say where a plugin
would have saved you work, match it against the catalog. It did not survive contact with the data.

- **4 of 199** skills overlap a catalog plugin.
- **1 of 108** measured gaps was answerable by a plugin.
- The four needs it surfaced had **no catalog equivalent** — no gateway supervisor, no repo auditor.

Ranking cannot fix a null relationship. Rather than ship a panel that dresses up `browserless` as a
gateway supervisor, it was cut. The gap ledger still records in the background
(`pluginscout_report`, `/gaps`), but the product is the pipeline above, where every claim is
checkable by running the validator.

## Tests

```bash
python3 -m pytest tests -q     # 62 passed
```

## Docs

- `docs/spec.md` — the long history: designs, pivots, and the measurements behind them.

MIT.
