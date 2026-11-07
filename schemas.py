"""Tool schemas. These descriptions are the only thing the model always sees — keep them tight."""

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

ALL = [CREATE, SOURCES, BUILT]
