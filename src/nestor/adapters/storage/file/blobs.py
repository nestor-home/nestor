"""Blobs on disk, addressed by the SHA-256 of their content: `<root>/ab/abcdef…`."""

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from nestor.core import ContractError
from nestor.modules.journal import BlobRef, BlobStore


class FileBlobStore(BlobStore):
    name = "file-blob-store"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    async def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        await asyncio.to_thread(self._write, self._path(digest), data)
        return BlobRef(digest, len(data), media_type)

    async def get(self, digest: str) -> bytes:
        try:
            return await asyncio.to_thread(self._path(digest).read_bytes)
        except FileNotFoundError:
            raise KeyError(digest) from None

    async def delete(self, digest: str) -> None:
        await asyncio.to_thread(self._path(digest).unlink, missing_ok=True)

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise ContractError(f"invalid blob digest {digest!r}")
        return self.root / digest[:2] / digest

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:  # atomic: never a half blob
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        Path(tmp.name).replace(path)
