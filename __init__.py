"""pluginscout — Hermes plugin entry point.

Wires: 3 tools, 3 hooks, a CLI subcommand, a slash command, and one bundled skill.
Sibling modules are loaded by path so this works whether Hermes imports the plugin as a
package or as a standalone directory.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"pluginscout_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def register(ctx) -> None:
    # The dashboard router runs in this same plugin-host process, but is imported as its own
    # module. Publishing ctx on the module lets plugin_api.py find it by scanning sys.modules
    # (see dashboard/plugin_api.py:_find_ctx) instead of reaching into host internals.

    tools = _load("tools", "tools.py")
    schemas = _load("schemas", "schemas.py")
    hooks = _load("hooks", "hooks.py")
    cli = _load("cli", "cli.py")

    for schema in schemas.ALL:
        ctx.register_tool(
            name=schema["name"],
            toolset="pluginscout",
            schema=schema,
            handler=tools.HANDLERS[schema["name"]],
            description=schema["description"].split(".")[0],
            emoji="\U0001F9ED",
        )

    ctx.register_hook("post_tool_call", hooks.on_post_tool_call)
    ctx.register_hook("on_skill_lifecycle", hooks.on_skill_lifecycle)
    ctx.register_hook("on_session_end", hooks.on_session_end)

    ctx.register_cli_command(
        "pluginscout",
        help="What the agent could not do: catalog-overlapping skills and recorded capability gaps",
        setup_fn=cli.setup,
        handler_fn=cli.run,
        description="Capability-gap instrument for Hermes (read-only; never installs)",
    )
    ctx.register_command("scout", handler=cli.slash, args_hint="[report|gaps|refresh|explain <target>]",
                         description="Capability gaps and catalog-overlapping skills")

    skills_root = _HERE / "skills"
    if skills_root.is_dir():
        for child in sorted(skills_root.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception:
                    logger.debug("pluginscout: could not register skill %s", child.name, exc_info=True)
