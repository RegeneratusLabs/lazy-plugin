"""Find the plugin context from a sibling module without reaching into host internals.

`register(ctx)` runs in the plugin host process. Modules imported by path (the dashboard router) do
not receive that ctx, but they share `sys.modules`. `__init__.register()` publishes the ctx under
`SCOUT_CTX`; this finds it. `llm` is explicitly part of the host's remote facade set, so calling it
from here is sanctioned rather than a hack.
"""

from __future__ import annotations

import sys

MARKER = "SCOUT_CTX"


def find() -> tuple[object | None, dict]:
    """(ctx, meta). Never raises: the page must still render when there is no ctx."""
    for name, module in list(sys.modules.items()):
        ctx = getattr(module, MARKER, None)
        if ctx is not None:
            return ctx, {"found": True, "module": name}
    return None, {"found": False, "scanned": len(sys.modules)}
