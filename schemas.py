"""Tool schemas. These descriptions are the only thing the model always sees — keep them tight."""

REPORT = {
    "name": "pluginscout_report",
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
    "name": "pluginscout_refresh",
    "description": (
        "Re-fetch the public Hermes plugin catalog and rebuild the local index. Use after the user "
        "installs or publishes a plugin, or when the report says the catalog is stale. "
        "One outbound GET; safe to call."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

EXPLAIN = {
    "name": "pluginscout_explain",
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
                       "description": "Skill name (as listed by pluginscout_report) or gap signature."},
        },
        "required": ["target"],
    },
}

BACKFILL = {
    "name": "pluginscout_backfill",
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

ALL = [REPORT, REFRESH, EXPLAIN, BACKFILL]
