"""A small state kept across restarts: written whole, and never left half-saved by a reader that stopped."""

import asyncio
from pathlib import Path

import pytest

from nestor.adapters.common.state import StateFile


async def test_a_save_cut_short_is_on_disk_for_whoever_reads_next(tmp_path: Path) -> None:
    """A source stopped while it saved where it was (a restart, a reader that gave up) must not hand the next start
    the previous state: it would serve again what was already taken."""
    file = StateFile(tmp_path / "feed.json")
    await file.save({"seen": 1})
    saving = asyncio.create_task(file.save({"seen": 2}))
    await asyncio.sleep(0)  # the write has started
    saving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await saving
    assert StateFile(tmp_path / "feed.json").load() == {"seen": 2}
