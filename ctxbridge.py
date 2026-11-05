"""Find the plugin's ctx from anywhere in this process.

Under ``plugins.isolation: host`` the plugin and its dashboard router are imported into the same
plugin-host process, but as different modules. ``__init__.register()`` publishes ctx as
``SCOUT_CTX`` on the plugin module; this scans ``sys.modules`` for that marker instead of guessing
a module name or reaching into host internals.
"""

from __future__ import annotations

import sys

MARKER = "SCOUT_CTX"


def find_ctx():
    """(ctx, meta). ``meta`` says whether we found it and why not, for the health route."""
    for module in list(sys.modules.values()):
        ctx = getattr(module, MARKER, None)
        if ctx is not None and hasattr(ctx, "llm"):
            return ctx, {"found": True, "module": getattr(module, "__name__", "?")}
    return None, {"found": False, "reason": "plugin not loaded in this process"}


def llm_available() -> bool:
    ctx, _ = find_ctx()
    return ctx is not None
