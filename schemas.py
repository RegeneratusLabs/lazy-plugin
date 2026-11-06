"""Tool schemas. These descriptions are the only thing the model always sees — keep them tight."""

REPORT = {
    "name": "lazyplugin_report",
    "description": (
        "Report real capability gaps for this profile: skills whose bodies drive a concrete tool, "
        "package, host or env var that a plugin in the public Hermes catalog already provides, plus "
        "a feed of recorded failures (command-not-found, tool errors, repeated shell-outs, skills the "
        "agent wrote to cope). Matching is exact-identifier only — no prose guessing, no LLM. "
        "Read-only: it never installs or edits anything. Use when the user asks what is missing, "
        "what plugin would help, why the agent keeps working around something, or which skills are "
        "redundant with the catalog."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["summary", "full", "json"],
                       "description": "summary = headline + top 5 (default); full = every match; "
                                      "json = the whole structure."},
            "min_match": {"type": "integer", "minimum": 1, "maximum": 10,
                          "description": "Minimum distinct matched identifiers to report a skill "
                                         "(default 1; raise for stricter evidence)."},
        },
        "required": [],
    },
}

REFRESH = {
    "name": "lazyplugin_refresh",
    "description": (
        "Re-fetch the public Hermes plugin catalog and rebuild the local index. Use after the user "
        "installs or publishes a plugin, or when the report says the catalog is stale. "
        "One outbound GET; safe to call."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

EXPLAIN = {
    "name": "lazyplugin_explain",
    "description": (
        "Explain one match or one recorded gap by its exact evidence: which identifiers matched, "
        "which catalog entry provides them, what that plugin needs in env, and the install command. "
        "Use before recommending a plugin so the user sees why, and to check the report is not "
        "bluffing. Pass a skill name or a gap signature (e.g. 'cmd:magick')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {"type": "string",
                       "description": "Skill name (as listed by lazyplugin_report) or gap signature."},
        },
        "required": ["target"],
    },
}

BACKFILL = {
    "name": "lazyplugin_backfill",
    "description": (
        "Mine past session transcripts on disk for capability gaps the agent hit before this plugin "
        "existed: missing binaries and missing Python packages only. Distinct from the live hooks — "
        "this is history, so a fresh install has real data on day one. Idempotent. "
        "Use when the gap feed is empty, after installing, or when the user asks what they have "
        "repeatedly reached for and not had."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 3650,
                     "description": "How far back to look (default 90)."},
            "max_sessions": {"type": "integer", "minimum": 1, "maximum": 5000,
                             "description": "Most recent JSONL transcripts to read (default 200)."},
            "source": {"type": "string", "enum": ["auto", "statedb", "jsonl"],
                       "description": "auto (default) prefers state.db and falls back to JSONL; "
                                      "statedb gives real timestamps and ~16x the records."},
        },
        "required": [],
    },
}

CONTRIBUTIONS = {
    "name": "lazyplugin_contributions",
    "description": (
        "Screen the agent's own recently created skills and say which are worth publishing to the "
        "Hermes community: publishable, needs scrubbing (naming the exact personal strings and line "
        "numbers), already covered by a catalog plugin, or keep private. Deterministic — no model "
        "call, no token spend. Pass package_name to stage a submission bundle (scrubbed SKILL.md, a "
        "README that credits the author, and CONTRIBUTION.json) in the plugin's outbox. Use when the "
        "user asks what they could contribute, which of their skills are reusable, or how to share "
        "something the agent learned."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 3650,
                     "description": "How recently the skill was created or patched (default 60)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50,
                      "description": "Most candidates to return (default 12)."},
            "package_name": {"type": "string",
                             "description": "Stage this skill as a submission bundle instead of just "
                                            "screening. Refuses anything scored private."},
            "mode": {"type": "string", "enum": ["package", "submit"],
                     "description": "With package_name: package (scrubbed copy only) or submit (also "
                                    "writes plugin.json, the plugin-catalog YAML entry and "
                                    "SUBMISSION.md with the PR steps). Default package."},
        },
        "required": [],
    },
}

READINESS = {
    "name": "lazyplugin_readiness",
    "description": (
        "Audit the installed Hermes plugins against the marketplace catalog's admission rules and "
        "say which could be submitted: manifest, version, description, LICENSE, declared repository, "
        "declared capabilities, self-updater scan (rule 3), and hermes plugins validate (rule 7). "
        "Returns ready/blocked per plugin with the exact blocker text, and can generate the "
        "plugin-catalog YAML entry plus the PR steps. Deterministic — no model call, nothing pushed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prepare": {"type": "string",
                        "description": "Generate the catalog entry + SUBMISSION.md for this plugin "
                                       "instead of only auditing."},
            "deep": {"type": "boolean",
                     "description": "Run the validator and registration probe per plugin "
                                    "(default true; each costs a subprocess)."},
        },
        "required": [],
    },
}

CREATE = {
    "name": "lazyplugin_create",
    "description": (
        "Build a Hermes plugin from a description, or from an existing skill or cron job. The model "
        "writes a spec (name, 1-5 tools, handler kind, params); fixed templates write the code; "
        "`hermes plugins validate` decides whether it ships. Writes to the plugin's outbox only — "
        "nothing is installed. Returns the spec, the files, and the validator's own output."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "idea": {"type": "string", "description": "What the plugin should do, in a sentence or two."},
            "source_kind": {"type": "string", "enum": ["skill", "cron"],
                            "description": "Build from something the user already does."},
            "source_name": {"type": "string",
                            "description": "Skill name or cron job name to build from."},
        },
        "required": [],
    },
}

SOURCES = {
    "name": "lazyplugin_sources",
    "description": (
        "List what a plugin could be built from: the agent-written skills in this profile and the "
        "scheduled cron jobs, with the details needed to pick one."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

BUILT = {
    "name": "lazyplugin_built",
    "description": "List plugins this tool has generated, with their outbox paths.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PENDING = {
    "name": "lazyplugin_pending",
    "description": (
        "Plugin build requests queued from the Lazy Plugin page, which cannot start a turn by "
        "itself. Call this when the user says they queued a plugin, then build each request with "
        "lazyplugin_create and answer the one question it cannot guess."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

ALL = [CREATE, SOURCES, BUILT, PENDING]
