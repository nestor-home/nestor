"""The journal as an account may read it: described, linked, filtered, counted, and limited to what it
reaches.

With `journal.read.all`, everything. With `journal.read.own`, what concerns the account's person and
the conversations they took part in (a session where they spoke, whoever else spoke in it).
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from nestor.admin.api.v1.models import JournalItem, Kind, LinksOut, MessageOut, OutcomeOut, People, ReasonOut
from nestor.admin.presentation import CATEGORIES, EventDescriber, Phrasebook, subject
from nestor.admin.state import AdminState
from nestor.core import SessionId
from nestor.core.events.codec import JSON
from nestor.modules.accounts import Principal, Scope
from nestor.modules.channels import Medium
from nestor.modules.cognition import TaskEnded, TaskStarted
from nestor.modules.cognition.delegation.events import TaskDelivered
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.conversation import AnswerCut, AssistantTurn, UserTurn
from nestor.modules.initiative import (
    Delivered,
    DeliveryConsidered,
    DeliveryFailed,
    WatchCreated,
    WatchEnded,
    WatchTriggered,
)
from nestor.modules.journal import Entry, EventLog, LogQuery

SCANNED = 1000  # entries read at once while filtering
PAGE_SCAN = 5000  # at most this many entries are read for one page
FACET_SCAN = 10_000  # facets count over at most this many of the newest entries in range
CAUSE_SCAN = 500  # how far back a cause is looked for
_DELIVERY = frozenset({DeliveryConsidered.event_type, Delivered.event_type, DeliveryFailed.event_type})


def _payload(entry: Entry) -> dict[str, JSON]:
    payload = entry.record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _text(value: JSON) -> str | None:
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True, slots=True, kw_only=True)
class Filters:
    """What a reader asked for. `kinds` empty means every kind; ids select one thread."""

    kinds: frozenset[str] = frozenset()
    person: str = ""
    channel: str = ""
    room: str = ""
    q: str = ""
    tone: str = ""
    since: datetime | None = None
    until: datetime | None = None
    session: str = ""
    task: str = ""
    watch: str = ""
    connection: str = ""
    satellite: str = ""

    def query(
        self,
        *,
        kinds: bool = True,
        after: int = 0,
        before: int | None = None,
        newest_first: bool = False,
        limit: int | None = None,
    ) -> LogQuery:
        """What the log can filter itself; the rest is checked on each item. Kinds are left out for
        facets, and when `other` is asked (events of no known kind have no type list)."""
        types = None
        if kinds and self.kinds and "other" not in self.kinds:
            types = frozenset().union(*(c.types for c in CATEGORIES if c.key in self.kinds))
        return LogQuery(
            types=types,
            session=SessionId(self.session) if self.session else None,
            since=self.since,
            until=self.until,
            after=after,
            before=before,
            newest_first=newest_first,
            limit=limit,
        )

    def failing(self, item: JournalItem) -> set[str]:
        """The facets whose selection this item fails (empty: the item is kept)."""
        failed = set()
        if self.kinds and item.kind not in self.kinds:
            failed.add("kinds")
        if self.person and self.person not in {p.id for p in item.people}:
            failed.add("people")
        if self.channel and self.channel not in item.channels:
            failed.add("channels")
        if self.room and item.room != self.room:
            failed.add("rooms")
        if self.tone and item.tone != self.tone:
            failed.add("tone")
        if self.q and not _matches(self.q, item):
            failed.add("q")
        links = item.links
        for wanted, got in (
            (self.task, links.task),
            (self.watch, links.watch),
            (self.connection, links.connection),
            (self.satellite, links.satellite),
        ):
            if wanted and got != wanted:
                failed.add("links")
        return failed


def _matches(q: str, item: JournalItem) -> bool:
    needle = q.casefold()
    reason = item.reason.text if item.reason else ""
    return any(needle in part.casefold() for part in (item.text, item.detail, item.detail_text, reason))


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
        mine = _payload(entry).get("person") == self.principal.person
        if entry.type == UserTurn.event_type and mine and entry.record.get("session"):
            self._sessions.add(str(entry.record["session"]))

    def sees(self, entry: Entry, people: Iterable[str]) -> bool:
        if self._everything:
            return True
        if not self.principal.can(Scope.JOURNAL_READ_OWN) or self.principal.person is None:
            return False
        return self.principal.person in set(people) or entry.record.get("session") in self._sessions


@dataclass(frozen=True, slots=True)
class _Rule:
    """Where an entry's cause is: an earlier entry of these types for which `matches` holds."""

    types: frozenset[str]
    matches: Callable[[Entry], bool]


def _same(key: str, value: JSON) -> Callable[[Entry], bool]:
    return lambda candidate: _payload(candidate).get(key) == value


def _cause_rule(entry: Entry) -> _Rule | None:
    payload = _payload(entry)
    kind = entry.type

    def of(cause: type, key: str) -> _Rule:
        return _Rule(frozenset({cause.event_type}), _same(key, payload.get(key)))  # ty: ignore[unresolved-attribute]

    if kind == ToolCompleted.event_type:
        return of(ToolCalled, "call_id")
    if kind == TaskEnded.event_type:
        return of(TaskStarted, "task_id")
    if kind == TaskDelivered.event_type:
        return of(TaskEnded, "task_id")
    if kind == WatchTriggered.event_type:
        return of(WatchCreated, "watch_id")
    if kind == WatchEnded.event_type:
        return of(WatchTriggered, "watch_id")
    if kind == AnswerCut.event_type:
        turn = payload.get("turn")
        return _Rule(frozenset({AssistantTurn.event_type}), lambda c: c.record.get("id") == turn)
    if kind == AssistantTurn.event_type:
        session = entry.record.get("session")
        return _Rule(frozenset({UserTurn.event_type}), lambda c: c.record.get("session") == session)
    if kind in (Delivered.event_type, DeliveryFailed.event_type):
        return of(DeliveryConsidered, "about")
    if kind == DeliveryConsidered.event_type:
        about = subject(str(payload.get("about", "")))
        if about["follow_up"] == "yes":
            first = str(payload.get("about", "")).removesuffix(" (follow-up)")
            return _Rule(frozenset({Delivered.event_type}), _same("about", first))
        if about["subject"] == "watch":
            return _Rule(frozenset({WatchTriggered.event_type}), _same("watch_id", about["id"]))
        if about["subject"] == "task":
            return _Rule(frozenset({TaskEnded.event_type}), _same("task_id", about["id"]))
    return None


@dataclass(slots=True)
class Facets:
    total: int = 0
    kinds: Counter[str] = field(default_factory=Counter)
    people: Counter[str] = field(default_factory=Counter)
    channels: Counter[str] = field(default_factory=Counter)
    rooms: Counter[str] = field(default_factory=Counter)
    moments: list[datetime] = field(default_factory=list)  # of the items kept, for the histogram
    truncated: bool = False


class Feed:
    def __init__(self, admin: AdminState, audience: Audience, filters: Filters, words: Phrasebook) -> None:
        nestor = admin.nestor
        self.admin, self.log = admin, nestor.journal.log
        self.audience, self.filters, self.words = audience, filters, words
        self.describer = EventDescriber(nestor.household, nestor.config.persona.name, words, admin.accounts)
        self.people = People(nestor.household)
        self._spoken = {c.channel_id for c in nestor.channels if c.medium is Medium.SPOKEN}
        self._channel_brands = {c.channel_id: c.brand for c in nestor.channels}
        self._executor_brands = {e.name: e.brand for e in nestor.executors}

    # -- one entry ------------------------------------------------------------------------------------

    def describe(self, entry: Entry) -> JournalItem | None:
        """The entry as the front shows it (without its cause), or `None` when this audience does not read it."""
        self.audience.learn(entry)
        line = self.describer.describe(entry)
        if not self.audience.sees(entry, line.people):
            return None
        payload = _payload(entry)
        message, text = self.words.summary(line.message)
        address = payload.get("address")
        room = line.room
        if room is None and isinstance(address, dict) and address.get("channel") in self._spoken:
            room = _text(address.get("conversation"))  # a spoken conversation is a room
        return JournalItem(
            position=entry.position,
            id=str(entry.record["id"]),
            at=line.at,
            type=entry.type,
            kind=cast(Kind, line.kind),
            kind_label=self.words.kind(line.kind),
            message=MessageOut.of(message),
            text=text,
            detail=line.detail,
            detail_message=MessageOut.of(line.detail_message) if line.detail_message else None,
            detail_text=self.words.text(line.detail_message) if line.detail_message else line.detail,
            reason=ReasonOut(message=MessageOut.of(line.reason), text=self.words.text(line.reason))
            if line.reason
            else None,
            tone=line.tone.value,
            people=[ref for p in sorted(line.people) if (ref := self.people.ref(p))],
            channels=sorted(line.channels),
            room=room,
            tool=line.tool,
            outcome=OutcomeOut(ok=line.outcome[0], duration_s=line.outcome[1]) if line.outcome else None,
            brand=self._brand(entry, sorted(line.channels)),
            links=self._links(entry),
            cause=None,
        )

    def _links(self, entry: Entry) -> LinksOut:
        payload = _payload(entry)
        device = payload.get("device")
        delivery = task = watch = None
        if entry.type in _DELIVERY:
            about = subject(str(payload.get("about", "")))
            if about["subject"] == "other":
                delivery = about["about"]
            else:
                delivery = f"{about['subject']}:{about['id']}"
                task = about["id"] if about["subject"] == "task" else None
                watch = about["id"] if about["subject"] == "watch" else None
        turn = str(entry.record["id"]) if entry.type == AssistantTurn.event_type else _text(payload.get("turn"))
        return LinksOut(
            session=_text(entry.record.get("session")),
            turn=turn,
            call=_text(payload.get("call_id")),
            task=_text(payload.get("task_id")) or task,
            watch=_text(payload.get("watch_id")) or watch,
            delivery=delivery,
            connection=_text(payload.get("connection_id")),
            satellite=_text(payload.get("device_id"))
            or (_text(device.get("id")) if isinstance(device, dict) else None),
            memory=_text(payload.get("memory_id")),
        )

    def _brand(self, entry: Entry, channels: list[str]) -> str | None:
        payload = _payload(entry)
        nestor = self.admin.nestor
        if channels:
            return self._channel_brands.get(channels[0])
        if (executor := payload.get("executor")) in self._executor_brands:
            return self._executor_brands[str(executor)]
        connections = nestor.connections
        if connections is not None:
            kind = payload.get("kind")
            connection = connections.connections.get(str(payload.get("connection_id", "")))
            connector = connections.connectors.get(str(connection.kind if connection else kind))
            if connector is not None and ("connection_id" in payload):
                return connector.info.brand
        device = payload.get("device")
        device_id = payload.get("device_id") or (device.get("id") if isinstance(device, dict) else None)
        if isinstance(device, dict) and isinstance(device.get("brand"), str):
            return str(device["brand"])
        satellite = next((s for s in nestor.pairing.satellites() if s.id == device_id), None)
        return satellite.brand if satellite else None

    async def cause(self, entry: Entry) -> int | None:
        rule = _cause_rule(entry)
        if rule is None:
            return None
        earlier = await self.log.read(
            LogQuery(types=rule.types, before=entry.position, newest_first=True, limit=CAUSE_SCAN)
        )
        return next((c.position for c in earlier if rule.matches(c)), None)

    async def item(self, entry: Entry) -> JournalItem | None:
        """The entry with its cause, when this audience reads it and the filters keep it."""
        item = self.describe(entry)
        if item is None or self.filters.failing(item):
            return None
        return item.model_copy(update={"cause": await self.cause(entry)})

    # -- many entries ------------------------------------------------------------------------------------

    async def page(self, *, before: int | None, limit: int) -> tuple[list[JournalItem], int | None]:
        """Newest first, strictly before position `before`; and the cursor of the next page, if any."""
        items: list[JournalItem] = []
        cursor, scanned = before, 0
        while scanned < PAGE_SCAN:
            entries = await self.log.read(self.filters.query(before=cursor, newest_first=True, limit=SCANNED))
            for index, entry in enumerate(entries):
                cursor, scanned = entry.position, scanned + 1
                if (item := await self.item(entry)) is not None:
                    items.append(item)
                if len(items) == limit:
                    more = index < len(entries) - 1 or len(entries) == SCANNED
                    return items, cursor if more else None
            if len(entries) < SCANNED:
                return items, None
        return items, cursor  # scanned enough for one page: the next one goes on from here

    async def after(self, position: int, *, limit: int = 200) -> tuple[list[JournalItem], int, bool]:
        """Entries after `position`, oldest first: the items to send, the last position read, whether more wait."""
        entries = await self.log.read(self.filters.query(after=position, limit=limit))
        items = [item for entry in entries if (item := await self.item(entry))]
        return items, entries[-1].position if entries else position, len(entries) == limit

    async def get(self, position: int) -> tuple[JournalItem, Entry] | None:
        """One entry by position, when this audience reads it (filters do not apply)."""
        found = await self.log.read(LogQuery(after=position - 1, before=position + 1))
        item = self.describe(found[0]) if found else None
        if item is None:
            return None
        return item.model_copy(update={"cause": await self.cause(found[0])}), found[0]

    async def facets(self) -> Facets:
        """Counts over the newest entries in range: each facet ignores its own selection."""
        facets = Facets()
        entries = await self.log.read(self.filters.query(kinds=False, newest_first=True, limit=FACET_SCAN))
        facets.truncated = len(entries) == FACET_SCAN
        for entry in entries:
            item = self.describe(entry)
            if item is None:
                continue
            failed = self.filters.failing(item)
            if not failed:
                facets.total += 1
                facets.moments.append(item.at)
            if failed <= {"kinds"}:
                facets.kinds[item.kind] += 1
            if failed <= {"people"}:
                facets.people.update(p.id for p in item.people)
            if failed <= {"channels"}:
                facets.channels.update(item.channels)
            if failed <= {"rooms"} and item.room:
                facets.rooms[item.room] += 1
        return facets

    async def last_position(self) -> int:
        newest = await self.log.read(LogQuery(limit=1, newest_first=True))
        return newest[0].position if newest else 0
