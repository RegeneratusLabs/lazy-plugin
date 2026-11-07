"""lazy-plugin — build a plugin from a description, a skill, or a cron job.

Wires: 3 tools, a CLI subcommand, a slash command, one bundled skill, and a native desktop page
with its own router.
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
    spec = importlib.util.spec_from_file_location(f"lazyplugin_{name}", _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def register(ctx) -> None:
    # The dashboard router runs in this same plugin-host process, but is imported as its own
    # module. Publishing ctx on the module lets plugin_api.py find it by scanning sys.modules
    # (see dashboard/plugin_api.py:_find_ctx) instead of reaching into host internals.

    # Sibling modules imported by path (dashboard router) share sys.modules but not ctx. `llm` is
    # part of the host's remote facade set, so publishing it is sanctioned, not a host-internals poke.
    globals()["SCOUT_CTX"] = ctx

    tools = _load("tools", "tools.py")
    schemas = _load("schemas", "schemas.py")

    for schema in schemas.ALL:
        ctx.register_tool(
            name=schema["name"],
            toolset="lazy-plugin",
            schema=schema,
            handler=tools.HANDLERS[schema["name"]],
            description=schema["description"].split(".")[0],
            emoji="\U0001F9ED",
        )

    skills_root = _HERE / "skills"
    if skills_root.is_dir():
        for child in sorted(skills_root.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception:
                    logger.debug("lazy-plugin: could not register skill %s", child.name, exc_info=True)
