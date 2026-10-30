"""OAuth authorisations started from the admin, waiting for the provider to send the browser back.

They are found by their `state`, not by the session: the session cookie is SameSite=Strict, so a
browser coming back from the provider (a cross-site navigation) does not send it. The `state` is
random, single use and short-lived, and the flow remembers which account started it.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from nestor.core import PersonId

FLOW_TTL_S = 600.0  # as long as `Connections` keeps the PKCE verifier


@dataclass(frozen=True, slots=True, kw_only=True)
class Flow:
    kind: str
    owner: PersonId | None
    account_id: str | None  # who started it: checked again when the browser comes back
    replaces: str | None = None  # the broken connection it reconnects, removed once this one works
    started: float = 0.0


class PendingFlows:
    def __init__(self, *, ttl_s: float = FLOW_TTL_S, limit: int = 100, clock: Callable[[], float] = time.monotonic):
        self._ttl_s, self._limit, self._clock = ttl_s, limit, clock
        self._flows: dict[str, Flow] = {}

    def add(self, state: str, *, kind: str, owner: PersonId | None, account_id: str | None, replaces: str | None):
        self._drop_stale()
        while len(self._flows) >= self._limit:
            del self._flows[next(iter(self._flows))]
        self._flows[state] = Flow(
            kind=kind, owner=owner, account_id=account_id, replaces=replaces, started=self._clock()
        )

    def take(self, state: str) -> Flow | None:
        """The flow of this state, once."""
        self._drop_stale()
        return self._flows.pop(state, None)

    def _drop_stale(self) -> None:
        now = self._clock()
        for state in [s for s, f in self._flows.items() if now - f.started > self._ttl_s]:
            del self._flows[state]
