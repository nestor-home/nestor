"""Where what a bench runs writes: a journal that keeps nothing, files kept in memory; a run's are thrown away."""

import hashlib

from nestor.core import Event
from nestor.modules.journal import BlobRef, BlobStore, Entry, EventLog, LogQuery


class Unlogged(EventLog):
    """Takes every event and keeps none."""

    name = "unlogged"

    def __init__(self) -> None:
        self.appended = 0

    async def append(self, event: Event) -> int:
        self.appended += 1
        return self.appended

    async def read(self, query: LogQuery) -> list[Entry]:
        return []


class MemoryBlobs(BlobStore):
    """Keeps a run's files, by content, until the run ends."""

    name = "memory-blobs"

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        self._blobs[digest] = data
        return BlobRef(digest, len(data), media_type)

    async def get(self, digest: str) -> bytes:
        return self._blobs[digest]

    async def delete(self, digest: str) -> None:
        self._blobs.pop(digest, None)
