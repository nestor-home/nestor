"""A small state an adapter keeps across restarts (where a feed was read up to, a page's last version), as one JSON
file in Nestor's data folder: backed up with it, written whole and atomically, so that a crash leaves the previous
state, never half of one."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class StateFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._writing = asyncio.Lock()  # one write at a time: the last state saved is the one kept

    def load(self) -> dict[str, Any]:
        """The state last saved; empty when there is none, or when it cannot be read (said in the log)."""
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            log.warning("%s could not be read (%s): starting afresh", self.path, error)
            return {}
        return state if isinstance(state, dict) else {}

    async def save(self, state: dict[str, Any]) -> None:
        text = json.dumps(state, ensure_ascii=False)
        async with self._writing:
            await asyncio.to_thread(self._write, text)

    def _write(self, text: str) -> None:
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        draft = self.path.with_name(f"{self.path.name}.tmp")
        with draft.open("w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())  # the new state is on disk before it replaces the old one
        os.replace(draft, self.path)
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)  # and so is the rename
        finally:
            os.close(descriptor)
