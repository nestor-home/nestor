"""Login throttling: a client that keeps failing waits before it may try again."""

import time
from collections.abc import Callable


class LoginThrottle:
    def __init__(
        self, *, failures: int = 5, window_s: float = 900.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._failures, self._window_s, self._clock = failures, window_s, clock
        self._attempts: dict[str, list[float]] = {}

    def wait_s(self, client: str) -> float:
        """0 when `client` may try now, else the seconds left before it may."""
        recent = self._recent(client)
        if len(recent) < self._failures:
            return 0.0
        return max(0.0, recent[0] + self._window_s - self._clock())

    def failed(self, client: str) -> None:
        self._attempts[client] = [*self._recent(client), self._clock()]

    def succeeded(self, client: str) -> None:
        self._attempts.pop(client, None)

    def _recent(self, client: str) -> list[float]:
        now = self._clock()
        recent = [t for t in self._attempts.get(client, ()) if now - t < self._window_s]
        if recent:
            self._attempts[client] = recent
        else:
            self._attempts.pop(client, None)
        return recent
