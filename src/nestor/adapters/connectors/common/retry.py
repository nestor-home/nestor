"""Pacing an inbound feed through provider trouble: back off on outages, wait long when the person must act."""

import asyncio
import logging

from nestor.core import ProviderError

log = logging.getLogger(__name__)


class Backoff:
    """Exponential delays between retries (1 s, 2 s, 4 s… up to `maximum_s`), back to the start after a success."""

    def __init__(self, initial_s: float = 1.0, maximum_s: float = 300.0, factor: float = 2.0) -> None:
        if initial_s <= 0 or maximum_s < initial_s or factor < 1:
            raise ValueError("backoff needs 0 < initial_s <= maximum_s and factor >= 1")
        self.initial_s, self.maximum_s, self.factor = initial_s, maximum_s, factor
        self._next = initial_s

    def next(self) -> float:
        delay = self._next
        self._next = min(self._next * self.factor, self.maximum_s)
        return delay

    def reset(self) -> None:
        self._next = self.initial_s


class Retry:
    """What a feed does after a failure: a transient one waits the next backoff delay; a permanent one
    (credentials refused, authorisation revoked) waits `blocked_s`, since only the person can fix it,
    then tries again so that the feed resumes on its own once they reconnected."""

    def __init__(self, source: str, backoff: Backoff, *, blocked_s: float = 600.0) -> None:
        self.source, self.backoff, self.blocked_s = source, backoff, blocked_s
        self._blocked = False

    async def after(self, error: ProviderError) -> None:
        if error.transient:
            delay = self.backoff.next()
            log.warning("%s: %s; retrying in %.1f s", self.source, error, delay)
        else:
            delay = self.blocked_s
            if not self._blocked:
                log.warning("%s paused until the account is reconnected: %s", self.source, error)
            self._blocked = True
        await asyncio.sleep(delay)

    def succeeded(self) -> None:
        if self._blocked:
            log.info("%s resumed", self.source)
        self._blocked = False
        self.backoff.reset()
