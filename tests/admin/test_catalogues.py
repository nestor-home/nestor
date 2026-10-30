"""Nothing the admin shows falls back to a raw name: every field of the configuration's forms, every
built-in event of the journal has its words in every locale Nestor ships, written without an em-dash."""

import dataclasses
import importlib
import logging
import pkgutil
import re
import types
import typing
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints

import pytest

import nestor.modules
from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.admin.presentation import EventDescriber, Phrasebook
from nestor.core import Event, PersonId
from nestor.core.i18n import Locale, Message
from nestor.modules.household import Household, Person
from nestor.modules.journal import Entry
from nestor.runtime import Registry
from nestor.runtime.editing import ConfigSchema

REGISTRY = Registry.installed()
LOCALIZER = FluentLocalizer(catalogue_dirs(["nestor", *REGISTRY.packages()]))
IDS = {
    locale: set(re.findall(r"^([A-Za-z][\w-]*) =", LOCALIZER.source(locale)[1], re.M)) for locale in LOCALIZER.locales
}
ENVELOPE = {"source", "session", "id", "at"}

for module in pkgutil.walk_packages(nestor.modules.__path__, "nestor.modules."):
    importlib.import_module(module.name)  # importing a module registers its events
BUILT_IN = sorted(
    (c for c in Event.types().values() if c.__module__.startswith("nestor.modules.")), key=lambda c: c.event_type
)


def test_nestor_ships_more_than_one_locale_and_every_event_module_is_seen() -> None:
    assert set(IDS) == {"en", "fr"}
    assert {"config.changed", "system.restart.requested", "account.locale.changed"} <= {c.event_type for c in BUILT_IN}


# -- the configuration's forms -----------------------------------------------------------------------------


def properties(node: Any, where: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every annotated property of a schema, with where it is."""
    if isinstance(node, dict):
        if isinstance(meta := node.get("x-nestor"), dict):
            yield where, meta
        for key, child in node.items():
            yield from properties(child, f"{where}.{key}")
    elif isinstance(node, list):
        for child in node:
            yield from properties(child, where)


def test_every_field_of_every_installed_plugin_has_a_title_in_every_locale() -> None:
    schema = ConfigSchema(REGISTRY)
    sections, slots = schema.sections(), schema.slots()
    found = [*properties(sections, "sections")]
    for key, slot in slots.items():
        found += properties(slot["kinds"], key)
    assert len(found) > 100, "the walk reaches nested settings"
    missing = {
        (locale, meta["title_id"])
        for _, meta in found
        for locale, ids in IDS.items()
        if meta["title_id"] not in ids and meta["fallback_title_id"] not in ids
    }
    missing |= {(locale, f"config-section-{s}") for s in sections for locale, ids in IDS.items()} - {
        (locale, i) for locale, ids in IDS.items() for i in ids
    }
    missing |= {(locale, f"config-slot-{s}") for s in slots for locale, ids in IDS.items()} - {
        (locale, i) for locale, ids in IDS.items() for i in ids
    }
    assert not missing, sorted(missing)


# -- the journal ------------------------------------------------------------------------------------------

HOUSEHOLD = Household([Person(id=PersonId("mathis"), name="Mathis")])


def sample(hint: Any, *, sparse: bool) -> Any:
    """A value for a payload field: with every optional value set, or as bare as the type allows."""
    while hasattr(hint, "__supertype__"):
        hint = hint.__supertype__
    origin, args = get_origin(hint), get_args(hint)
    if origin in (typing.Union, types.UnionType):
        return None if sparse else sample(next(a for a in args if a is not type(None)), sparse=sparse)
    if origin is tuple:
        return () if sparse else (sample(args[0], sparse=sparse),)
    if origin in (dict, Mapping, typing.Mapping):
        return {} if sparse else {"room": "salon"}
    if hint is Message:
        return Message.of("delivery-in-room", person="Mathis", room="salon")
    if isinstance(hint, type) and issubclass(hint, Enum):
        return list(hint)[0 if sparse else -1]
    if dataclasses.is_dataclass(hint):
        hints = get_type_hints(hint)
        return hint(**{f.name: sample(hints[f.name], sparse=sparse) for f in dataclasses.fields(hint)})
    if hint is str:
        return "" if sparse else "mathis"
    return {float: 0.5, int: 0 if sparse else 2, bool: not sparse, datetime: datetime(2026, 10, 30, tzinfo=UTC)}[hint]


def entry(cls: type[Event], *, sparse: bool) -> Entry:
    hints = get_type_hints(cls)
    payload = {f.name: sample(hints[f.name], sparse=sparse) for f in dataclasses.fields(cls) if f.name not in ENVELOPE}
    return Entry(position=1, record=cls(source="test", **payload).to_record())


@pytest.mark.parametrize("sparse", [False, True], ids=["full", "sparse"])
@pytest.mark.parametrize("cls", BUILT_IN, ids=lambda c: c.event_type)
def test_every_built_in_event_is_told_in_every_locale(
    cls: type[Event], sparse: bool, caplog: pytest.LogCaptureFixture
) -> None:
    for locale in IDS:
        words = Phrasebook(LOCALIZER, Locale(locale))
        line = EventDescriber(HOUSEHOLD, "Richie", words).describe(entry(cls, sparse=sparse))
        said = [m for m in (line.message, line.detail_message) if m is not None]
        assert all(m.id in IDS[locale] for m in said), (locale, [m.id for m in said])
        caplog.clear()  # an unknown capability keeps its name on purpose: only the sentences are checked
        with caplog.at_level(logging.WARNING):
            texts = [words.text(m) for m in said]
        assert not caplog.records, [r.getMessage() for r in caplog.records]
        assert all(t and "{" not in t for t in texts), texts


def test_no_shipped_sentence_uses_an_em_dash() -> None:
    for locale in LOCALIZER.locales:
        _, text = LOCALIZER.source(locale)
        assert "—" not in text, [line for line in text.splitlines() if "—" in line]
