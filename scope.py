"""Carry the caller's contextvars into a worker thread, and say plainly when a key is missing.

One Hermes process serves many profiles. Anything running outside a turn — our build threads — must
keep the profile scope it was started under; a bare `threading.Thread` starts with empty context, so
the first secret read raises UnscopedSecretError (what a build looked like from the page).

`contextvars.copy_context()` is the same propagation `asyncio.to_thread` relies on. If the caller
had no scope to inherit, the build still runs and `secret_probe` reports the missing key as a plain
sentence instead of a traceback.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable, Optional


def run_in_scope(fn: Callable[..., Any], *args: Any) -> Any:
    """Run *fn* in a copy of the current context, so profile-scoped reads keep working."""
    return contextvars.copy_context().run(fn, *args)


def secret_probe(name: str = "OPENCODE_GO_API_KEY") -> Optional[bool]:
    """True when this process can read *name* right now; None when the scope API is unavailable."""
    try:
        from agent import secret_scope

        value = secret_scope.get_secret(name)
        return bool(value and str(value).strip())
    except Exception:
        return None
