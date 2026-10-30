"""Locales and messages."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import NewType

Locale = NewType("Locale", str)  # BCP 47: "fr-FR", "en"

type Argument = str | int | float


@dataclass(frozen=True, slots=True)
class Message:
    """Something to tell a person, by id, with its arguments; rendered by a `Localizer`.

    Ids are kebab-case and namespaced by what owns them (`delivery-in-room`, `voice-stt-down`);
    arguments are plain values so messages can travel in events and over the API.
    """

    id: str
    args: Mapping[str, Argument] = field(default_factory=dict)

    @classmethod
    def of(cls, id: str, /, **args: Argument) -> "Message":
        return cls(id, args)


def negotiate(wanted: Locale | str, available: Iterable[Locale], default: Locale) -> Locale:
    """The best available locale for `wanted`: exact, then same language, then `default`
    (BCP 47 lookup, RFC 4647 §3.4, without wildcards)."""
    options = list(available)
    by_tag = {o.casefold(): o for o in options}
    tag = str(wanted).replace("_", "-").casefold()
    while tag:
        if tag in by_tag:
            return by_tag[tag]
        same_language = [o for o in options if o.casefold().split("-")[0] == tag]
        if same_language:
            return same_language[0]
        tag = tag.rpartition("-")[0]
    return default
