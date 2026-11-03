"""Blobs on disk: the blob store contract, and a digest that could escape the folder."""

from pathlib import Path

import pytest

from nestor.adapters.storage.file import FileBlobStore
from nestor.core import ContractError
from nestor.testing.journal import BlobStoreContract


class TestFileBlobStore(BlobStoreContract):
    @pytest.fixture(autouse=True)
    def _root(self, tmp_path: Path) -> None:
        self.root = tmp_path / "blobs"

    def blob_store(self) -> FileBlobStore:
        return FileBlobStore(self.root)


async def test_an_invalid_blob_digest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ContractError):
        await FileBlobStore(tmp_path).get("../../etc/passwd")
