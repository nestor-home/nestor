"""Versioned domain events: the vocabulary of the event log.

Every observable effect in Nestor is an event. A module declares its events in one line:

    class TaskStarted(Event, event_type="task.started"):
        task_id: str
        objective: str

The subclass becomes a frozen, keyword-only dataclass registered under its type, so the log
can turn any record back into the right class. Changing a payload means bumping `version`
(`event_type="task.started", version=2`) and overriding `upgrade`, which turns an older record's
payload into the next version's: the log is never rewritten, records are upgraded as they are read.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, ClassVar, dataclass_transform, get_type_hints

from nestor.core.events import codec
from nestor.core.exceptions import ContractError
from nestor.core.shared import SessionId, new_id, utc_now

type Record = dict[str, codec.JSON]

_ENVELOPE = frozenset({"source", "session", "id", "at"})


@dataclass_transform(frozen_default=True, kw_only_default=True, field_specifiers=(field,))
@dataclass(frozen=True, kw_only=True)
class Event:
    """Something that happened, attributed to a `source` component and optionally a session."""

    event_type: ClassVar[str] = ""
    version: ClassVar[int] = 1
    _registry: ClassVar[dict[str, type["Event"]]] = {}

    source: str
    session: SessionId | None = None
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)

    def __init_subclass__(cls, *, event_type: str, version: int = 1, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if event_type in Event._registry:
            owner = Event._registry[event_type].__qualname__
            raise ContractError(f"event type {event_type!r} is already defined by {owner}")
        cls.event_type, cls.version = event_type, version
        dataclass(frozen=True, kw_only=True)(cls)
        Event._registry[event_type] = cls

    def to_record(self) -> Record:
        payload = {f.name: codec.encode(getattr(self, f.name)) for f in fields(self) if f.name not in _ENVELOPE}
        return {
            "type": self.event_type,
            "version": self.version,
            "id": self.id,
            "at": self.at.isoformat(),
            "source": self.source,
            "session": self.session,
            "payload": payload,
        }

    @staticmethod
    def from_record(record: Record) -> "Event":
        try:
            cls = Event._registry[str(record["type"])]
        except KeyError:
            raise ContractError(f"unknown event type {record.get('type')!r}") from None
        version, payload = record["version"], record["payload"]
        if not isinstance(version, int) or version > cls.version or version < 1:
            raise ContractError(
                f"{cls.event_type} record is version {version}, code expects {cls.version}: migrate the log"
            )
        while version < cls.version:  # older records are upgraded one version at a time
            if not isinstance(payload, dict):
                break
            payload, version = cls.upgrade(version, payload), version + 1
        hints = get_type_hints(cls)
        if not isinstance(payload, dict) or not payload.keys() <= hints.keys() - _ENVELOPE:
            raise ContractError(f"{cls.event_type} record has an invalid payload: {payload!r}")
        session = record["session"]
        return cls(
            source=str(record["source"]),
            session=SessionId(str(session)) if session is not None else None,
            id=str(record["id"]),
            at=datetime.fromisoformat(str(record["at"])),
            **{name: codec.decode(value, hints[name]) for name, value in payload.items()},
        )

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, codec.JSON]) -> dict[str, codec.JSON]:
        """The payload of a record of `version`, as version `version + 1` expects it. An event that bumps
        its version overrides this; by default an older record cannot be read."""
        raise ContractError(f"{cls.event_type} records of version {version} cannot be upgraded: migrate the log")

    @staticmethod
    def types() -> dict[str, type["Event"]]:
        """All registered event types (read-only view for the log and the dashboard)."""
        return dict(Event._registry)
