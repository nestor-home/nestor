"""What the sherpa-onnx adapters share: a model downloaded once from its release and checked against its pinned
sha256, an archive unpacked where the model is read from."""

import asyncio
import hashlib
import tarfile
from pathlib import Path

import httpx

from nestor.core import ProviderError


async def fetch(url: str, path: Path, sha256: str, *, provider: str) -> None:
    """Download `url` to `path` once; a file that does not match `sha256` is never kept."""
    if path.is_file() and await asyncio.to_thread(file_sha256, path) == sha256:
        return
    partial = path.with_name(f"{path.name}.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    try:
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, connect=10)) as client,
            client.stream("GET", url) as response,
        ):
            if response.is_error:
                raise ProviderError(provider, f"HTTP {response.status_code} for {path.name}", transient=True)
            with partial.open("wb") as out:
                async for chunk in response.aiter_bytes():
                    digest.update(chunk)
                    out.write(chunk)
    except httpx.HTTPError as error:
        partial.unlink(missing_ok=True)
        raise ProviderError(provider, f"cannot download {path.name} ({error})", transient=True) from None
    except ProviderError:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != sha256:
        partial.unlink(missing_ok=True)
        raise ProviderError(provider, f"{path.name} does not match its sha256", transient=False)
    partial.replace(path)


def unpack(archive: Path, into: Path) -> None:
    """Unpack a `.tar.bz2` release into `into`, nothing outside it (the `data` filter refuses links and paths that
    leave it); done once, marked by a file of its own."""
    done = into / ".unpacked"
    if done.is_file():
        return
    with tarfile.open(archive, "r:bz2") as tar:
        tar.extractall(into, filter="data")
    done.write_text(archive.name)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
