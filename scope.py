"""Carry the caller's contextvars into a worker thread, and find the provider key honestly.

Two things this got wrong before, both worth keeping written down:

1. A bare `threading.Thread` starts with empty contextvars. One gateway process serves several
   profiles, so the first secret read raised UnscopedSecretError. `copy_context().run()` is the
   same propagation `asyncio.to_thread` uses, and it is what a worker needs.
2. The probe asked for `OPENCODE_GO_API_KEY` while this build's opencode-go provider reads
   `OPENCODE_ZEN_API_KEY`. A probe that guesses the variable name blocks builds that would have
   worked, so it checks every name the provider has used and reports "cannot tell" otherwise.
"""

from __future__ import annotations

import contextvars
import os
from typing import Any, Callable, Iterable, Optional

# names seen across builds of the opencode-go provider; the first that resolves wins
PROVIDER_KEY_NAMES = ("OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY")


def run_in_scope(fn: Callable[..., Any], *args: Any) -> Any:
    """Run *fn* in a copy of the current context, so profile-scoped reads keep working."""
    return contextvars.copy_context().run(fn, *args)


def secret_probe(names: Optional[Iterable[str]] = None) -> Optional[bool]:
    """True when a provider key is readable; None means "cannot tell, do not block".

    None is the important case: a wrong answer here turns a working build into a refusal.
    """
    saw_api = False
    for name in (names or PROVIDER_KEY_NAMES):
        try:
            from agent import secret_scope

            saw_api = True
            value = secret_scope.get_secret(name)
        except Exception:
            value = os.environ.get(name)
        if value and str(value).strip():
            return True
    return False if saw_api else None
