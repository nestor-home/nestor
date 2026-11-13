"""What the feed and page sources share: addresses checked on an interval, a few at a time, each with a state kept
across restarts in a file of its own (`<data>/inbound/<source>/`), so that saving one never rewrites the others.

The first check of an address only takes its state (what is already there is not new); `start` takes the first
states of all addresses at once, each within `deadline_s`, so that what arrives once Nestor runs is new. An item is
taken when the next one is asked for: only then is the state that follows it saved, so an item whose triage was cut
short (a stop, a cancellation) comes again after a restart, and one that was handled never does. A check that fails
in any way (network, an error status, an address off the internet, a body that cannot be read, the deadline) is
logged and retried at the next round: `items()` never ends with an error of the web.
"""

import asyncio
import hashlib
import logging
from abc import abstractmethod
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import Field, PositiveInt

from nestor.adapters.common.state import StateFile
from nestor.adapters.common.web import PublicWeb, WebError
from nestor.modules.initiative import InboundEventSource, Incoming
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings

log = logging.getLogger(__name__)

AT_ONCE = 4  # addresses checked together: polite to the network, quick for a long list

type State = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Watched:
    name: str  # how people call it: "LWN", "the lamp at Ikea"
    url: str


@dataclass(frozen=True, slots=True)
class Check:
    """What a check found: each item with the state once it is taken, and the state once all are (the last
    item's)."""

    found: list[tuple[Incoming, State]] = field(default_factory=list)
    state: State = field(default_factory=dict)


class Polled(InboundEventSource):
    kind: str

    def __init__(
        self,
        name: str,
        watched: Sequence[Watched],
        web: PublicWeb,
        folder: Path,
        *,
        every_s: float,
        deadline_s: float = 60.0,
    ) -> None:
        self.name = name
        self.kinds = (self.kind,)
        self.follows = {self.kind: tuple(w.name for w in watched)}
        self._watched, self._web, self._folder = tuple(watched), web, folder
        self._every_s, self._deadline_s = every_s, deadline_s
        self._files = {
            w.url: StateFile(folder / f"{hashlib.sha256(w.url.encode()).hexdigest()[:16]}.json") for w in watched
        }
        self._states: dict[str, State] = {}
        self._at_once = asyncio.Semaphore(AT_ONCE)

    async def start(self) -> None:
        kept = {f.path for f in self._files.values()}
        for stale in self._folder.glob("*.json") if self._folder.is_dir() else ():
            if stale not in kept:  # an address no longer watched
                stale.unlink(missing_ok=True)
        self._states = {url: state for url, file in self._files.items() if (state := file.load())}
        await asyncio.gather(*(self._check(w) for w in self._watched if w.url not in self._states))

    async def close(self) -> None:
        await self._web.aclose()

    async def items(self) -> AsyncGenerator[Incoming]:
        while True:
            rounds = await asyncio.gather(*(self._check(w) for w in self._watched))
            for watched, found in zip(self._watched, rounds, strict=True):
                for item, after in found:
                    yield item
                    await self._save(watched, after)  # taken: the next one is asked for
            await asyncio.sleep(self._every_s)

    async def _check(self, watched: Watched) -> list[tuple[Incoming, State]]:
        """The items a check of `watched` found; its state saved now when there is none to take first."""
        known = self._states.get(watched.url)
        try:
            async with self._at_once, asyncio.timeout(self._deadline_s):
                check = await self.check(watched, known)
        except WebError as error:
            log.warning("%s could not check %s: %s", self.name, watched.name, error)
            return []
        except Exception:  # whatever went wrong with this address, the others and the next round go on
            log.exception("%s could not check %s", self.name, watched.name)
            return []
        if not check.found:
            await self._save(watched, check.state)
            return []
        return [*check.found[:-1], (check.found[-1][0], check.state)]

    async def _save(self, watched: Watched, state: State) -> None:
        if self._states.get(watched.url) != state:
            self._states[watched.url] = state
            await self._files[watched.url].save(state)

    @abstractmethod
    async def check(self, watched: Watched, known: State | None) -> Check:
        """What is new at `watched` since `known` (`None`: never checked, nothing is new); a `WebError` when it
        cannot be read."""


class Address(AdapterSettings):
    name: str = Field(min_length=1)  # how people call it: "LWN", "the lamp at Ikea"
    url: str = Field(min_length=1)


class PolledSettings(AdapterSettings):
    """What every polled source takes besides its addresses and interval."""

    timeout_s: float = Field(default=20.0, gt=0, json_schema_extra={"advanced": True})  # a whole check
    max_bytes: PositiveInt = Field(default=5_000_000, json_schema_extra={"advanced": True})

    def web(self, accept: str) -> PublicWeb:
        return PublicWeb(accept=accept, timeout_s=self.timeout_s, max_bytes=self.max_bytes)


def to_watch(addresses: Sequence[Address]) -> list[Watched]:
    return [Watched(a.name, a.url) for a in addresses]


def state_folder(services: Services, name: str) -> Path:
    """Where the source `name` keeps the state of each address."""
    return services.data_dir / "inbound" / name
