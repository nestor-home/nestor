"""`@name` in a message, whatever the channel: a person of the household, a room, an executor, a connected account.

The modules that own these things say what can be named and what naming it asks (`MentionSource`); this registry
gives each a handle unique for whoever writes, finds the names a message holds, and tells the model what they name in
the turn's instructions. Names are what people type, never ids, and are read loosely: `@Mathilde`, `@mathilde` and
`@mathïlde` are one, a handle or any alias. A web page offers the list as people type; a messaging app needs nothing:
the text is enough.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import replace

from nestor.modules.conversation.ports import ContextProvider, Layer, MentionSource, Sections, TurnContext
from nestor.modules.conversation.types import Mentioned
from nestor.modules.household import Person

HANDLE = re.compile(r"(?<![\w@])@([\w-]*\w)")  # not in an e-mail address; a trailing hyphen is punctuation


class Mentions(ContextProvider):
    """`sources` in the order their handles are given out: an earlier source keeps a handle two would share."""

    def __init__(self, sources: Iterable[MentionSource] = ()) -> None:
        self._sources = tuple(sources)

    def available(self, person: Person | None) -> list[Mentioned]:
        """What `person` can name, each with its own handle."""
        return [mentioned for mentioned, _ in self._offered(person)]

    def named(self, text: str, person: Person | None) -> tuple[Mentioned, ...]:
        """What `text` names, once each, in the order written; a handle nothing answers to is left as words."""
        if "@" not in text:
            return ()
        offered = self.available(person)
        aliases: dict[str, list[Mentioned]] = {}
        for mentioned in offered:
            for name in {_key(n) for n in mentioned.aliases}:
                aliases.setdefault(name, []).append(mentioned)
        # an alias two things share names neither; a handle always wins over an alias
        names = {name: found[0] for name, found in aliases.items() if len(found) == 1}
        names.update({_key(m.handle): m for m in offered})
        found: dict[str, Mentioned] = {}
        for name in HANDLE.findall(text):
            if (mentioned := names.get(_key(name))) is not None:
                found.setdefault(mentioned.handle, mentioned)
        return tuple(found.values())

    async def context(self, turn: TurnContext) -> Sections:
        if not turn.mentions:
            return {}
        sources = {(m.kind, m.id): source for m, source in self._offered(turn.person)}
        lines = [
            f"- @{m.handle}: {source.instruction(m)}"
            for m in turn.mentions
            if (source := sources.get((m.kind, m.id))) is not None
        ]
        return {Layer.TURN: "The message names, with @:\n" + "\n".join(lines)} if lines else {}

    def _offered(self, person: Person | None) -> Sequence[tuple[Mentioned, MentionSource]]:
        taken: set[str] = set()
        offered: list[tuple[Mentioned, MentionSource]] = []
        for source in self._sources:
            for mentioned in source.mentionable(person):
                handle = _unique(_key(mentioned.handle), taken)
                taken.add(handle)
                offered.append((replace(mentioned, handle=handle), source))
        return offered


def _key(name: str) -> str:
    """A name as it is compared: without case or accents, words joined by hyphens (`Salle à manger` →
    `salle-a-manger`)."""
    plain = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[a-z0-9_]+", plain.replace("_", "-")))


def _unique(handle: str, taken: set[str]) -> str:
    if handle not in taken:
        return handle
    n = 2
    while f"{handle}-{n}" in taken:
        n += 1
    return f"{handle}-{n}"
