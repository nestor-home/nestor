"""The installed suites: every `nestor.benches` entry point, built-in or from another package."""

from collections.abc import Iterable, Iterator
from importlib.metadata import entry_points
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.ports import Suite
from nestor.core import ContractError
from nestor.core.i18n import Message

ENTRY_POINTS = "nestor.benches"


class Suites:
    def __init__(self, suites: Iterable[Suite[Any, Any]] = ()) -> None:
        self._suites: dict[str, Suite[Any, Any]] = {}
        for suite in suites:
            if suite.name in self._suites:
                raise ContractError(f"two suites are named {suite.name!r}")
            self._suites[suite.name] = suite

    @classmethod
    def installed(cls) -> "Suites":
        found = []
        for entry in entry_points(group=ENTRY_POINTS):
            suite = entry.load()
            if not isinstance(suite, Suite):
                raise ContractError(f"entry point {entry.name!r} ({entry.value}) is not a nestor bench Suite")
            found.append(suite)
        return cls(found)

    def __iter__(self) -> Iterator[Suite[Any, Any]]:
        return iter(sorted(self._suites.values(), key=lambda s: s.name))

    def packages(self) -> tuple[str, ...]:
        """Top-level packages providing suites: where their `locales/` catalogues are looked for."""
        return tuple(dict.fromkeys(type(s).__module__.partition(".")[0] for s in self._suites.values()))

    def get(self, name: str) -> Suite[Any, Any]:
        try:
            return self._suites[name]
        except KeyError:
            known = ", ".join(sorted(self._suites)) or "-"
            raise BenchError(Message.of("bench-unknown-suite", suite=name, known=known)) from None
