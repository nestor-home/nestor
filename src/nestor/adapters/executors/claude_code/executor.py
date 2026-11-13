"""Claude Code, run headless, running Nestor's tasks."""

import asyncio
import json
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nestor.adapters.executors.claude_code.cli import COMMAND, TOOLS, PermissionMode
from nestor.adapters.executors.claude_code.stream import REPORTING, tool_step
from nestor.adapters.executors.common import (
    FILES_INSTRUCTIONS,
    INSTRUCTIONS,
    MAX_FILE_BYTES,
    REPORT_SCHEMA,
    Report,
    Unreadable,
)
from nestor.adapters.executors.process import Child
from nestor.core import Health
from nestor.core.i18n import Message
from nestor.modules.cognition import Executor, Outcome, Progress


class ClaudeCodeExecutor(Executor):
    """Delegates objectives to Claude Code in its working directory.

    `description` states what this Claude Code can really do with the tools it is allowed: the assistant promises
    exactly that. A task has no time limit; a stop gives the process `stop_timeout_s` before it is killed.
    """

    name = "claude-code"
    brand = "claude-code"

    def __init__(
        self,
        command: Sequence[str] = COMMAND,
        *,
        working_directory: Path,
        description: str,
        instructions: str = INSTRUCTIONS,
        model: str | None = None,
        permission_mode: PermissionMode = PermissionMode.DONT_ASK,
        allowed_tools: Sequence[str] = TOOLS,
        disallowed_tools: Sequence[str] = (),
        max_budget_usd: float | None = None,
        api_key: str | None = None,
        stop_timeout_s: float = 10.0,
        max_file_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self.description = description
        self._command, self._cwd = tuple(command), working_directory.expanduser().resolve()  # as Claude Code sees it
        self._instructions, self._model, self._mode = instructions, model, permission_mode
        self._allowed, self._disallowed, self._budget = tuple(allowed_tools), tuple(disallowed_tools), max_budget_usd
        self._env = {"ANTHROPIC_API_KEY": api_key} if api_key else {}
        self._stop_timeout_s, self._max_file_bytes = stop_timeout_s, max_file_bytes

    def health(self) -> Health:
        return Health.STARTED if shutil.which(self._command[0]) else Health.UNAVAILABLE

    def health_detail(self) -> Message | None:
        return (
            None if self.health() is Health.STARTED else Message.of("health-executor-unreachable", executor=self.name)
        )

    def details(self) -> dict[str, str]:
        return {"permission_mode": self._mode.value} | ({"model": self._model} if self._model else {})

    async def run(self, objective: str, progress: Progress) -> Outcome:
        session = str(uuid.uuid4())
        try:
            child = await Child.start([*self._command, *self._arguments(session)], cwd=self._cwd, env=self._env)
        except OSError as error:
            return Outcome.failed(f"Claude Code could not start: {error.strerror or error}")
        progress(f"session {session}")
        try:
            assert child.process.stdin is not None
            child.process.stdin.write(objective.encode())
            child.process.stdin.close()
            result = await self._follow(child, progress)
            await child.wait()
        except asyncio.CancelledError:
            await asyncio.shield(child.stop(self._stop_timeout_s))  # confirmed: the process has exited
            return Outcome.cancelled()
        if result is None:
            said = f": {child.said}" if child.said else ""
            return Outcome.failed(f"Claude Code ended without a result (exit {child.process.returncode}){said}")
        if result.get("is_error") or result.get("subtype") != "success":
            return Outcome.failed(str(result.get("result") or result.get("subtype") or "Claude Code failed"))
        report = Report.of(result.get("structured_output") or result.get("result") or "")
        return await report.outcome(str(self._cwd), self._read)

    def _arguments(self, session: str) -> list[str]:
        arguments = [
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--session-id",
            session,
            "--permission-mode",
            self._mode.value,
            "--append-system-prompt",
            self._instructions + FILES_INSTRUCTIONS,
            "--json-schema",
            json.dumps(REPORT_SCHEMA),
        ]
        if self._model:
            arguments += ["--model", self._model]
        if self._allowed:
            arguments += ["--allowedTools", ",".join(self._allowed)]
        if self._disallowed:
            arguments += ["--disallowedTools", ",".join(self._disallowed)]
        if self._budget is not None:
            arguments += ["--max-budget-usd", str(self._budget)]
        return arguments

    async def _follow(self, child: Child, progress: Progress) -> dict[str, Any] | None:
        """Reads the stream to its end; the `result` message, if one came."""
        result: dict[str, Any] | None = None
        async for line in child.lines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "result":
                result = message
            elif message.get("type") == "assistant":
                for used in (message.get("message") or {}).get("content") or ():
                    if isinstance(used, dict) and used.get("type") == "tool_use" and used.get("name") != REPORTING:
                        progress(tool_step(used))
        return result

    async def _read(self, path: str) -> bytes:
        resolved, root = Path(path).resolve(), self._cwd.resolve()
        if not resolved.is_relative_to(root):  # a link out of the working directory
            raise Unreadable("outside the working directory")
        if not resolved.is_file():
            raise Unreadable("not a file" if resolved.exists() else "missing")
        if resolved.stat().st_size > self._max_file_bytes:
            raise Unreadable(f"larger than {self._max_file_bytes} bytes")
        return await asyncio.to_thread(resolved.read_bytes)
