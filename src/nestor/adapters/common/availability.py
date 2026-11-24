"""How an adapter tells that an outside service stopped answering and came back: once each, with how long it was gone,
so that a night's restart of a home server leaves two lines in the log, not one per attempt."""

import logging
import time
from collections.abc import Callable


class Availability:
    """Whether a service an adapter depends on answers. `lost` logs a WARNING when it stops answering, with what that
    means `meanwhile` ("its tools are missing until it answers"), then the attempts that follow at DEBUG; `back` logs
    at INFO when it answers again, with how long it was gone."""

    def __init__(self, logger: logging.Logger, name: Callable[[], str], meanwhile: str) -> None:
        """`name`: the adapter's, read when it logs (a component is named once assembled)."""
        self._logger, self._name, self._meanwhile = logger, name, meanwhile
        self._since: float | None = None  # when it stopped answering

    def lost(self, reason: object) -> None:
        if self._since is not None:
            self._logger.debug("%s: still unavailable: %s", self._name(), reason)
            return
        self._since = time.monotonic()
        self._logger.warning("%s: unavailable, %s: %s", self._name(), self._meanwhile, reason)

    def back(self, detail: str = "") -> bool:
        """It answers again: said once, when it had been lost; whether it had."""
        if self._since is None:
            return False
        gone, self._since = time.monotonic() - self._since, None
        self._logger.info("%s: back after %s%s", self._name(), _duration(gone), f", {detail}" if detail else "")
        return True


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes = seconds / 60
    return f"{minutes:.0f} min" if minutes < 60 else f"{minutes / 60:.1f} h"
