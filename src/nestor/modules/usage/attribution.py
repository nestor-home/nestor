"""On whose behalf and why a call is made: set where the work starts, read by the meter when a model is called.

A turn says it answers a person on a channel; an alert says it sorts what came in. What runs inside, models, tools,
the tasks it starts in the background, inherits it, and may say more (`attributed(purpose=CallPurpose.TITLE)`). A call
made with nothing said is recorded as `unattributed`, a fault the ledger shows rather than hides.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Any

from nestor.modules.usage.types import Attribution

NOTHING_SAID = Attribution()
_CURRENT: ContextVar[Attribution | None] = ContextVar("nestor_attribution", default=None)


def attribution() -> Attribution:
    """What the work in progress said of itself."""
    return _CURRENT.get() or NOTHING_SAID


@contextmanager
def attributed(**said: Any) -> Generator[Attribution]:
    """Within the block, the work is the current one with `said` (fields of `Attribution`) set over it."""
    now = replace(attribution(), **said)
    token = _CURRENT.set(now)
    try:
        yield now
    finally:
        _CURRENT.reset(token)


def attribute(**said: Any) -> None:
    """For the rest of the task in progress: the current work with `said` set over it, as the task learns of itself
    (who spoke, once known). Only for a task that is that work and nothing else: an answer's own worker, a request's
    handler, never a loop that serves many."""
    _CURRENT.set(replace(attribution(), **said))
