"""Values of the journal: logged entries, queries over them and references to stored blobs."""

from dataclasses import dataclass
from datetime import datetime

from nestor.core import Event, Record, SessionId


@dataclass(frozen=True, slots=True)
class Entry:
    """A logged event and its position: positions only grow, so they order and page the log."""

    position: int
    record: Record

    @property
    def type(self) -> str:
        return str(self.record["type"])

    def event(self) -> Event:
        return Event.from_record(self.record)


@dataclass(frozen=True, slots=True, kw_only=True)
class LogQuery:
    """Which entries to read. Every criterion is optional; entries come in log order."""

    types: frozenset[str] | None = None
    session: SessionId | None = None
    since: datetime | None = None
    until: datetime | None = None
    after: int = 0  # position cursor: entries strictly after it
    limit: int | None = None
    newest_first: bool = False


@dataclass(frozen=True, slots=True)
class BlobRef:
    """A stored file, addressed by the SHA-256 of its content."""

    digest: str
    size: int
    media_type: str
