"""A child process an executor talks to through its standard streams: Codex's app-server, Claude Code.

It runs in a process group of its own, so a stop reaches the commands it started; it is asked to stop, then
killed. Its output is read line by line, a line longer than the limit skipped rather than ending the read (the
child would block on a full pipe); the last line it wrote on its error output is kept, to say why it ended.
"""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

LINE_LIMIT = 64 * 1024 * 1024
SAID_LENGTH = 300


class Child:
    """Start it with `start`; `lines` reads its output, `stop` ends it (and its group) for good."""

    def __init__(self, name: str, process: asyncio.subprocess.Process) -> None:
        self.name, self.process = name, process
        self._said: str | None = None
        self._errors = asyncio.create_task(self._read_errors(), name=f"{name} stderr")

    @classmethod
    async def start(
        cls, command: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
    ) -> "Child":
        """Raises `OSError` when the command cannot start (not installed, not executable)."""
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **env} if env else None,
            limit=LINE_LIMIT,
            start_new_session=True,
        )
        return cls(command[0], process)

    @property
    def said(self) -> str | None:
        """The last line it wrote on its error output."""
        return self._said

    def ended(self) -> str:
        """Why it is gone, for an error message."""
        return f"{self.name} ended" + (f": {self._said}" if self._said else "")

    def lines(self) -> AsyncIterator[bytes]:
        """Its output, line by line, until it closes."""
        assert self.process.stdout is not None
        return _lines(self.process.stdout, self.name)

    async def stop(self, timeout_s: float) -> None:
        """Asks its group to stop, kills it after `timeout_s`; returns once it has exited."""
        process = self.process
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout_s)
            except TimeoutError:
                logger.warning("%s did not stop when asked: killed", self.name)
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        await self.wait()

    async def wait(self) -> None:
        """Until it has exited and its error output is read."""
        await self.process.wait()
        with contextlib.suppress(asyncio.CancelledError):
            await self._errors

    async def _read_errors(self) -> None:
        assert self.process.stderr is not None
        async for line in _lines(self.process.stderr, self.name):
            if text := line.decode(errors="replace").strip():
                self._said = text[:SAID_LENGTH]


async def _lines(stream: asyncio.StreamReader, name: str) -> AsyncIterator[bytes]:
    while True:
        try:
            line = await stream.readline()
        except ValueError:  # beyond the limit: the reader dropped it, the rest of it comes as a fragment
            logger.warning("%s: a line longer than %d bytes was skipped", name, LINE_LIMIT)
            continue
        if not line:
            return
        yield line
