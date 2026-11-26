"""A memory: one fact, filed in a place, with where it came from.

Places are a small fixed tree, as Claude's memory tool works on a directory: `people/<person>`, `home` (the house
itself: rooms, devices, works), `household` (the family's shared life: routines, pets, contacts),
`projects/<name>` (something with an end: a renovation, a trip, a purchase) and `topics/<name>` (a lasting
interest: the garden, wine). The first level is fixed; Nestor names the projects and topics.
"""

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from nestor.core import ContractError, PersonId, new_id, utc_now
from nestor.modules.channels import Address


class Shelf(StrEnum):
    """The first level of a place: fixed."""

    PEOPLE = "people"
    HOME = "home"
    HOUSEHOLD = "household"
    PROJECTS = "projects"
    TOPICS = "topics"


NAMED = frozenset({Shelf.PEOPLE, Shelf.PROJECTS, Shelf.TOPICS})  # the shelves holding named places
_SEPARATORS = re.compile(r"[\s_/]+")
_LEFT_OUT = re.compile(r"[^\w-]+")


@dataclass(frozen=True, slots=True, order=True)
class Place:
    """Where a memory is filed: a shelf, and a name on the shelves that hold several (a person's id, a project's or a
    topic's name). Such a shelf without a name is the whole shelf: memories are searched in it, never filed."""

    shelf: Shelf
    name: str | None = None

    def __post_init__(self) -> None:
        if self.name and self.shelf not in NAMED:
            raise ContractError(f"{self.shelf.value} takes no name")

    def __str__(self) -> str:
        return f"{self.shelf.value}/{self.name}" if self.name else self.shelf.value

    @classmethod
    def parse(cls, text: str) -> "Place":
        """`people/lea`, `home`, `household`, `projects/roof-works`, `topics/garden`; a project's or topic's name is
        written in lowercase words joined by hyphens, whatever is given ("Roof works" is `roof-works`)."""
        shelf, _, name = text.strip().strip("/").partition("/")
        try:
            kind = Shelf(shelf.strip().lower())
        except ValueError:
            raise ContractError(f"no place {text!r}: {', '.join(s.value for s in Shelf)}") from None
        if kind is Shelf.PEOPLE:
            return cls(kind, name.strip() or None)
        return cls(kind, slug(name) or None)

    @classmethod
    def of(cls, person: PersonId | None) -> "Place":
        """A person's place, or the household's for no one in particular."""
        return cls(Shelf.PEOPLE, person) if person else HOUSEHOLD

    @property
    def whole(self) -> bool:
        """A shelf of named places, without a name: it holds places, never a memory."""
        return self.shelf in NAMED and not self.name

    @property
    def person(self) -> PersonId | None:
        """Whom it is about, when it is a person's place."""
        return PersonId(self.name) if self.shelf is Shelf.PEOPLE and self.name else None

    @property
    def label(self) -> str:
        """The words its name adds to a search (`roof works`): those of a project or a topic."""
        return self.name.replace("-", " ") if self.name and self.shelf in (Shelf.PROJECTS, Shelf.TOPICS) else ""

    def holds(self, other: "Place") -> bool:
        """Whether `other` is this place, or one on this shelf when this one names none."""
        return other == self or (self.name is None and other.shelf is self.shelf)


HOME = Place(Shelf.HOME)
HOUSEHOLD = Place(Shelf.HOUSEHOLD)


def slug(text: str) -> str:
    """A name as places keep it: lowercase words joined by hyphens, accents and letters of any script kept."""
    words = _LEFT_OUT.sub("", _SEPARATORS.sub("-", unicodedata.normalize("NFC", text.strip().lower())))
    return "-".join(w for w in words.split("-") if w)


class Retirement(StrEnum):
    """Why a memory was retired: no longer used, its record kept in the journal."""

    ENDED = "ended"  # what it was tied to ended
    STALE = "stale"  # the upkeep found it outdated or overridden
    MERGED = "merged"  # the upkeep merged it into another saying the same


@dataclass(frozen=True, slots=True, kw_only=True)
class Memory:
    """`tied_to` is what it only holds while it runs (`task:<id>`): it is retired when that ends."""

    text: str
    place: Place = HOUSEHOLD
    source: Address | None = None  # the conversation it was learnt in
    told_by: PersonId | None = None
    tied_to: str | None = None
    id: str = field(default_factory=lambda: new_id()[:12])
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def about(self) -> PersonId | None:
        """Whom it is about: a person's place; `None` for every other place, which the household shares."""
        return self.place.person

    def corrected(self, text: str) -> "Memory":
        return replace(self, text=text, updated_at=utc_now())

    def moved(self, place: Place) -> "Memory":
        return replace(self, place=place, updated_at=utc_now())
