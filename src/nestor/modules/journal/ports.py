"""Storage ports of the journal: the event log and the blob store."""

from abc import ABC, abstractmethod

from nestor.core import Component, Event
from nestor.modules.journal.types import BlobRef, Entry, LogQuery


class EventLog(Component, ABC):
    """Append-only storage of events.

    Contract (checked by `nestor.testing.journal.EventLogContract`):
    - `append` is durable when it returns and gives a position greater than every previous one;
    - an event id is logged once: appending it again is a `ContractError`;
    - `read` returns entries matching every criterion of the query (positions strictly between
      `after` and `before`), in log order (or reversed), at most `limit` of them from that end;
    - entries are never rewritten; records keep the exact payload that was appended.
    """

    @abstractmethod
    async def append(self, event: Event) -> int: ...

    @abstractmethod
    async def read(self, query: LogQuery) -> list[Entry]: ...


class BlobStore(Component, ABC):
    """Heavy files (audio, images, captures) addressed by content, referenced from events.

    Contract (checked by `nestor.testing.journal.BlobStoreContract`):
    - storing the same content twice yields the same reference and keeps one copy;
    - `get` returns exactly the stored bytes, and raises `KeyError` for an unknown or deleted digest;
    - `delete` of an unknown digest is a no-op.
    """

    @abstractmethod
    async def put(self, data: bytes, media_type: str) -> BlobRef: ...

    @abstractmethod
    async def get(self, digest: str) -> bytes: ...

    @abstractmethod
    async def delete(self, digest: str) -> None: ...
