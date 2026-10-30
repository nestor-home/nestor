"""The journal as an account may read it: described in French, filtered, and limited to what it reaches.

With `journal.read.all`, everything. With `journal.read.own`, what concerns the account's person and
the conversations they took part in (a session where they spoke, whoever else spoke in it).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from nestor.admin.api.v1.models import LINKS, JournalItem, Kind, People
from nestor.admin.presentation import CATEGORIES, EventDescriber, Line
from nestor.admin.state import AdminState
from nestor.core import PersonId
from nestor.modules.accounts import Principal, Scope
from nestor.modules.conversation import UserTurn
from nestor.modules.journal import Entry, EventLog, LogQuery

SCANNED = 1000  # entries read per page before filtering


@dataclass(frozen=True, slots=True, kw_only=True)
class Filters:
    category: str = ""
    person: str = ""
    channel: str = ""

    @property
    def types(self) -> frozenset[str] | None:
        category = next((c for c in CATEGORIES if c.key == self.category), None)
        return category.types if category else None

    def keeps(self, line: Line) -> bool:
        if self.person and PersonId(self.person) not in line.people:
            return False
        return not self.channel or self.channel in line.channels


class Audience:
    """Which entries a principal reads; it learns the conversations they join while a stream is open."""

    def __init__(self, principal: Principal, sessions: set[str]) -> None:
        self.principal, self._sessions = principal, sessions
        self._everything = principal.can(Scope.JOURNAL_READ_ALL)

    @classmethod
    async def of(cls, principal: Principal, log: EventLog) -> "Audience":
        if principal.can(Scope.JOURNAL_READ_ALL) or principal.person is None:
            return cls(principal, set())
        turns = await log.read(LogQuery(types=frozenset({UserTurn.event_type})))
        audience = cls(principal, set())
        for entry in turns:
            audience.learn(entry)
        return audience

    def learn(self, entry: Entry) -> None:
        payload = entry.record.get("payload")
        mine = isinstance(payload, dict) and payload.get("person") == self.principal.person
        if entry.type == UserTurn.event_type and mine and entry.record.get("session"):
            self._sessions.add(str(entry.record["session"]))

    def sees(self, entry: Entry, line: Line) -> bool:
        if self._everything:
            return True
        if not self.principal.can(Scope.JOURNAL_READ_OWN) or self.principal.person is None:
            return False
        return self.principal.person in line.people or entry.record.get("session") in self._sessions


class Feed:
    def __init__(self, admin: AdminState, audience: Audience, filters: Filters) -> None:
        nestor = admin.nestor
        self.log = nestor.journal.log
        self.audience, self.filters = audience, filters
        self.describer = EventDescriber(nestor.household, nestor.config.persona.name, admin.accounts)
        self.people = People(nestor.household)

    def item(self, entry: Entry) -> JournalItem | None:
        """The entry as the front shows it, or `None` when this audience does not read it or it is filtered out."""
        self.audience.learn(entry)
        line = self.describer.describe(entry)
        if not self.audience.sees(entry, line) or not self.filters.keeps(line):
            return None
        payload = entry.record.get("payload")
        fields = payload if isinstance(payload, dict) else {}
        device = fields.get("device")
        links = {k: v if isinstance(v := fields.get(k), str) else None for k in LINKS}
        device_id = device.get("id") if isinstance(device, dict) else None
        if isinstance(device_id, str):
            links["device_id"] = device_id  # pairing events carry the whole device
        session = entry.record.get("session")
        return JournalItem(
            position=entry.position,
            id=str(entry.record["id"]),
            at=line.at,
            type=entry.type,
            kind=cast(Kind, line.category_key),
            kind_label=line.category,
            summary=line.title,
            detail=line.detail,
            reason=line.reason,
            tone=line.tone.value,
            people=[ref for p in sorted(line.people) if (ref := self.people.ref(p))],
            channels=sorted(line.channels),
            session=str(session) if session else None,
            **links,
        )

    async def page(self, *, before: int | None, limit: int) -> tuple[list[JournalItem], int | None]:
        """Newest first, strictly before position `before`; and the cursor of the next page, if any."""
        until = None
        if before is not None:
            anchors = await self.log.read(LogQuery(after=before - 1, limit=1))
            if not anchors:
                return [], None
            # positions follow time: entries up to the anchor's instant, then strictly before its position
            until = datetime.fromisoformat(str(anchors[0].record["at"])) + timedelta(microseconds=1)
        entries = await self.log.read(LogQuery(types=self.filters.types, until=until, limit=SCANNED, newest_first=True))
        items, cursor = [], None
        for entry in entries:
            if before is not None and entry.position >= before:
                continue
            cursor = entry.position
            if item := self.item(entry):
                items.append(item)
                if len(items) == limit:
                    break
        more = len(items) == limit or len(entries) == SCANNED
        return items, cursor if more else None

    async def after(self, position: int, *, limit: int = 200) -> tuple[list[JournalItem], int, bool]:
        """Entries after `position`, oldest first: the items to send, the last position read, whether more wait."""
        entries = await self.log.read(LogQuery(types=self.filters.types, after=position, limit=limit))
        items = [item for entry in entries if (item := self.item(entry))]
        return items, entries[-1].position if entries else position, len(entries) == limit

    async def last_position(self) -> int:
        newest = await self.log.read(LogQuery(limit=1, newest_first=True))
        return newest[0].position if newest else 0
