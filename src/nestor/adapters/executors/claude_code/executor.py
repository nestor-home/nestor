"""Claude Code, run headless, running Nestor's tasks."""

import asyncio
import functools
import json
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nestor.adapters.executors.claude_code.cli import COMMAND, TOOLS, PermissionMode
from nestor.adapters.executors.claude_code.stream import REPORTING, tool_step, user_message
from nestor.adapters.executors.common import (
    FILES_INSTRUCTIONS,
    INSTRUCTIONS,
    MAX_FILE_BYTES,
    QUESTION_INSTRUCTIONS,
    REPORT_SCHEMA,
    Report,
    Unreadable,
)
from nestor.adapters.executors.process import Child
from nestor.core import Capabilities, Health
from nestor.core.i18n import Message
from nestor.modules.cognition.delegation import (
    CONTINUE,
    STEER,
    Assignment,
    Executor,
    NestorAccess,
    NestorTools,
    Outcome,
    Progress,
)


@dataclass(slots=True)
class _Turn:
    """A turn's process; whether it still takes instructions (until its first result); the session the next turn can
    go on in: the one it resumed, or its own once Claude Code started it (`init`)."""

    child: Child
    session: str | None
    open: bool = True
    results: list[dict[str, Any]] = field(default_factory=list)


class ClaudeCodeExecutor(Executor):
    """Delegates objectives to Claude Code in its working directory.

    `description` states what this Claude Code can really do with the tools it is allowed: the assistant promises
    exactly that. A turn has no time limit; a stop gives the process `stop_timeout_s` before it is killed.
    """

    name = "claude-code"
    brand = "claude-code"
    nestor_tools = NestorTools.PASSED
    capabilities = Capabilities.of(CONTINUE, STEER)

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
        self._turns: dict[str, _Turn] = {}  # by session: the turns that work now

    def health(self) -> Health:
        return Health.STARTED if shutil.which(self._command[0]) else Health.UNAVAILABLE

    def health_detail(self) -> Message | None:
        return (
            None if self.health() is Health.STARTED else Message.of("health-executor-unreachable", executor=self.name)
        )

    def details(self) -> dict[str, str]:
        return {"permission_mode": self._mode.value} | ({"model": self._model} if self._model else {})

    async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
        """In the task's own folder under the working directory, where the files sent with the instruction are
        placed; in the session of the turns before when there is one."""
        try:
            folder, placed = await self._prepare(assignment)
        except OSError as error:
            return Outcome.failed(
                f"the task's folder could not be made: {error.strerror or error}", session=assignment.session
            )
        with tempfile.TemporaryDirectory(prefix="nestor-claude-") as private:  # its key never on a command line
            servers = _mcp_config(assignment.access, Path(private)) if assignment.access else None
            return await self._run(assignment, assignment.brief(str(folder), placed), progress, servers, folder)

    async def steer(self, handle: str, instruction: str) -> bool:
        """A user message to the session's process: Claude Code reads it between two steps of the turn. Not once the
        turn has given its result: a message then would start a turn nobody follows."""
        turn = self._turns.get(handle)
        stdin = turn.child.process.stdin if turn and turn.open else None
        if stdin is None or stdin.is_closing():
            return False
        try:
            stdin.write(user_message(instruction))
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError):  # it ended meanwhile
            return False
        return True

    async def _prepare(self, assignment: Assignment) -> tuple[Path, list[str]]:
        """The task's folder, made on its first turn, and the names of the files placed in it."""
        folder, placed = self._cwd / assignment.folder, []
        await asyncio.to_thread(folder.mkdir, exist_ok=True)
        async for name, data in assignment.placed():  # plain names, never twice
            await asyncio.to_thread((folder / name).write_bytes, data)
            placed.append(name)
        return folder, placed

    async def _run(
        self, assignment: Assignment, brief: str, progress: Progress, servers: Path | None, folder: Path
    ) -> Outcome:
        session = assignment.session or str(uuid.uuid4())
        try:
            child = await Child.start(
                [*self._command, *self._arguments(assignment.session, session, servers)], cwd=folder, env=self._env
            )
        except OSError as error:
            return Outcome.failed(f"Claude Code could not start: {error.strerror or error}", session=assignment.session)
        turn = self._turns[session] = _Turn(child, assignment.session)
        progress.attach(session)
        progress(f"session {session}")
        try:
            assert child.process.stdin is not None
            child.process.stdin.write(user_message(brief))
            await self._follow(turn, session, progress)
            await child.wait()
        except asyncio.CancelledError:
            await asyncio.shield(child.stop(self._stop_timeout_s))  # confirmed: the process has exited
            return Outcome.stopped(session=turn.session)
        finally:
            turn.open = False
            self._turns.pop(session, None)
        return await self._outcome(turn, folder)

    async def _outcome(self, turn: _Turn, folder: Path) -> Outcome:
        """From its results: one, or more when an instruction came as the turn ended and Claude Code answered it in a
        turn of its own. Their reports are joined; the last says whether it failed or asks."""
        session, child = turn.session, turn.child
        if not turn.results:
            said = f": {child.said}" if child.said else ""
            return Outcome.failed(
                f"Claude Code ended without a result (exit {child.process.returncode}){said}", session=session
            )
        last = turn.results[-1]
        if last.get("is_error") or last.get("subtype") != "success":
            error = str(last.get("result") or last.get("subtype") or "Claude Code failed")
            return Outcome.failed(error, session=session)
        reports = [Report.of(r.get("structured_output") or r.get("result") or "") for r in turn.results]
        report = Report(
            "\n\n".join(r.text for r in reports if r.text),
            tuple(f for r in reports for f in r.files),
            reports[-1].question,
        )
        return await report.outcome(str(folder), functools.partial(self._read, folder), session=session)

    def _arguments(self, resumed: str | None, session: str, servers: Path | None) -> list[str]:
        arguments = [
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            *(("--resume", resumed) if resumed else ("--session-id", session)),
            "--permission-mode",
            self._mode.value,
            "--append-system-prompt",
            self._instructions + FILES_INSTRUCTIONS + QUESTION_INSTRUCTIONS,
            "--json-schema",
            json.dumps(REPORT_SCHEMA),
        ]
        if self._model:
            arguments += ["--model", self._model]
        allowed = list(self._allowed)
        if servers:
            arguments += ["--mcp-config", str(servers)]
            allowed.append(NESTOR_TOOLS)
        if allowed:
            arguments += ["--allowedTools", ",".join(allowed)]
        if self._disallowed:
            arguments += ["--disallowedTools", ",".join(self._disallowed)]
        if self._budget is not None:
            arguments += ["--max-budget-usd", str(self._budget)]
        return arguments

    async def _follow(self, turn: _Turn, session: str, progress: Progress) -> None:
        """Reads the stream to its end, keeping each `result` message. The first ends the turn: its input is closed,
        and Claude Code exits once it has answered what was already sent."""
        stdin = turn.child.process.stdin
        async for line in turn.child.lines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "system" and message.get("subtype") == "init":
                turn.session = session
            elif message.get("type") == "result":
                turn.results.append(message)
                if turn.open and stdin is not None:
                    turn.open = False
                    stdin.close()
            elif message.get("type") == "assistant":
                for used in (message.get("message") or {}).get("content") or ():
                    if isinstance(used, dict) and used.get("type") == "tool_use" and used.get("name") != REPORTING:
                        progress(tool_step(used))

    async def _read(self, folder: Path, path: str) -> bytes:
        """A file the task made, within its own `folder`."""
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(folder.resolve()):  # a link out of the task's folder
            raise Unreadable("outside the working directory")
        if not resolved.is_file():
            raise Unreadable("not a file" if resolved.exists() else "missing")
        if resolved.stat().st_size > self._max_file_bytes:
            raise Unreadable(f"larger than {self._max_file_bytes} bytes")
        return await asyncio.to_thread(resolved.read_bytes)


NESTOR_TOOLS = "mcp__nestor"  # every tool of the `nestor` server


def _mcp_config(access: NestorAccess, folder: Path) -> Path:
    """Nestor's MCP server for one turn, in a file only this user reads: its key stays off the command line."""
    path = folder / "mcp.json"  # the folder is the turn's own, readable by this user only
    server = {"type": "http", "url": access.url, "headers": {"Authorization": f"Bearer {access.key}"}}
    path.write_text(json.dumps({"mcpServers": {"nestor": server}}))
    path.chmod(0o600)
    return path
