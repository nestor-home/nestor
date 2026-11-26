"""Codex, through `codex app-server`, running Nestor's tasks."""

import asyncio
import base64
import contextlib
import logging
import posixpath
from collections.abc import Mapping, Sequence
from typing import Any

from nestor import __version__
from nestor.adapters.executors.codex.protocol import (
    COMMAND,
    DECLINED,
    ENDED,
    Sandbox,
    final_answer,
    item_step,
    unknown_thread,
)
from nestor.adapters.executors.common import (
    CODING_REPORT,
    INSTRUCTIONS,
    MAX_FILE_BYTES,
    REPORT_SCHEMA,
    Report,
    Unreadable,
    described,
)
from nestor.adapters.executors.jsonrpc import Closed, Message, RpcError, StdioRpc
from nestor.core import Capabilities, ContractError, Health, ProviderError
from nestor.core.i18n import Message as Said
from nestor.modules.cognition.delegation import (
    CONTINUE,
    RESUME,
    STEER,
    Assignment,
    Handle,
    NestorAccess,
    NestorTools,
    Outcome,
    Progress,
    RemoteExecutor,
    SessionLost,
)

logger = logging.getLogger(__name__)

RECONNECT_S = (1.0, 5.0, 30.0)  # waits before following again a turn whose session was lost


class CodexExecutor(RemoteExecutor):
    """Delegates tasks to Codex, a thread per task and a turn per instruction; its turns are followed again after a
    restart, and an instruction given while one works is steered into it.

    `description` states what this Codex can really do (its sandbox, its tools, its MCP servers): the assistant
    promises exactly that. Requests time out after `timeout_s`; a turn itself has no time limit.
    """

    name = "codex"
    brand = "codex"
    nestor_tools = NestorTools.PASSED
    capabilities = Capabilities.of(RESUME, CONTINUE, STEER)

    def __init__(
        self,
        command: Sequence[str] = COMMAND,
        *,
        working_directory: str,
        description: str,
        instructions: str = INSTRUCTIONS,
        model: str | None = None,
        sandbox: Sandbox = Sandbox.WORKSPACE_WRITE,
        config: Mapping[str, Any] | None = None,
        timeout_s: float = 30.0,
        stop_timeout_s: float = 10.0,
        poll_interval_s: float = 0.5,
        max_file_bytes: int = MAX_FILE_BYTES,
        reconnect_s: Sequence[float] = RECONNECT_S,
    ) -> None:
        self.description = description
        self._command, self._cwd = tuple(command), working_directory
        self._instructions, self._model, self._sandbox, self._config = instructions, model, sandbox, config
        self._timeout_s, self._stop_timeout_s, self._poll_interval_s = timeout_s, stop_timeout_s, poll_interval_s
        self._max_file_bytes, self._reconnect_s = max_file_bytes, tuple(reconnect_s)
        self._rpc: StdioRpc | None = None
        self._joined: set[str] = set()  # the threads this session follows
        self._loaded: set[str] = set()  # the threads this session started or resumed: a turn starts there directly
        self._opening = asyncio.Lock()
        self._started = self._unreachable = False

    def health(self) -> Health:
        return Health.UNAVAILABLE if self._unreachable else Health.STARTED

    def health_detail(self) -> Said | None:
        return Said.of("health-executor-unreachable", executor=self.name) if self._unreachable else None

    def details(self) -> dict[str, str]:
        return {"sandbox": self._sandbox.value} | ({"model": self._model} if self._model else {})

    async def start(self) -> None:
        self._started = True  # Codex is reached on first use: Nestor starts while its host is down

    async def close(self) -> None:
        self._started = False
        rpc, self._rpc = self._rpc, None
        if rpc is not None:
            await rpc.close()

    async def submit(self, assignment: Assignment) -> Handle:
        """A turn in the task's thread, in the task's own folder under the working directory, where the files sent
        with the instruction are placed: the thread starts with the task's first turn, and later turns go on in it
        (resumed first when this session has not loaded it: after a restart, or on another session)."""
        folder = posixpath.join(self._cwd, assignment.folder)
        try:
            rpc = await self._session()
            await self._call(rpc, "fs/createDirectory", {"path": folder, "recursive": True})  # there already: fine
            placed = []
            async for file, data in assignment.placed():  # plain names, never twice
                encoded = (await asyncio.to_thread(base64.b64encode, data)).decode()  # up to 27 MB: off the loop
                await self._call(rpc, "fs/writeFile", {"path": posixpath.join(folder, file), "dataBase64": encoded})
                placed.append(file)
            settings = self._thread_settings(assignment.access, folder)
            if (thread := assignment.session) is None:
                thread = str((await self._call(rpc, "thread/start", settings))["thread"]["id"])
            elif thread not in self._loaded:
                await self._call(rpc, "thread/resume", {"threadId": thread, "excludeTurns": True} | settings)
            self._loaded.add(thread)
            self._join(rpc, thread)
            turn = await self._call(
                rpc,
                "turn/start",
                {
                    "threadId": thread,
                    "input": [{"type": "text", "text": assignment.brief(folder, placed)}],
                    "outputSchema": REPORT_SCHEMA,
                },
            )
            return Handle(f"{thread}:{turn['turn']['id']}:{assignment.folder}", thread)
        except (KeyError, TypeError) as error:
            raise ProviderError(self.name, f"unexpected reply from Codex: {error!r}", transient=False) from None
        except RpcError as error:
            if unknown_thread(error):
                raise SessionLost(self.name, f"Codex no longer has this thread: {error}", transient=False) from None
            raise ProviderError(self.name, f"submission refused: {error}", transient=False) from None
        except (Closed, TimeoutError) as error:
            raise ProviderError(self.name, f"submission failed: {described(error)}", transient=True) from None

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        if (parsed := _parsed(ref)) is None:
            return Outcome.failed(f"not a Codex task reference: {ref!r}")
        thread, turn, folder = parsed
        waits = iter(self._reconnect_s)
        while True:
            try:
                return await self._follow(thread, turn, posixpath.join(self._cwd, folder), progress)
            except (Closed, TimeoutError, ProviderError) as error:  # the session is lost, the turn may go on
                if (wait_s := next(waits, None)) is None:
                    return Outcome.failed(f"lost contact with Codex: {described(error)}")
                logger.warning("%s: lost contact with Codex, following again in %ss (%s)", self.name, wait_s, error)
                await asyncio.sleep(wait_s)
            except RpcError as error:
                if unknown_thread(error):  # gone with the turn: the next turn starts a new thread
                    return Outcome.lost(f"Codex no longer has this thread: {error}")
                return Outcome.failed(f"Codex refused: {error}")
            except (KeyError, TypeError, ValueError) as error:  # not the protocol: a missing field, bad base64
                return Outcome.failed(f"unexpected reply from Codex: {error!r}")

    async def stop(self, ref: str) -> bool:
        if (parsed := _parsed(ref)) is None:
            return False
        thread, turn, _ = parsed
        try:
            async with asyncio.timeout(self._stop_timeout_s):
                rpc = await self._session()
                with contextlib.suppress(RpcError):  # no turn running there: how it ended says if it was stopped
                    await self._call(rpc, "turn/interrupt", {"threadId": thread, "turnId": turn})
                while (
                    status := (await self._turn(rpc, thread, turn, view="notLoaded") or {}).get("status")
                ) not in ENDED:
                    await asyncio.sleep(self._poll_interval_s)
                return status == "interrupted"
        except (TimeoutError, ProviderError, RpcError, Closed, KeyError, TypeError):
            return False

    async def steer(self, handle: str, instruction: str) -> bool:
        """`turn/steer`, on the turn the handle names only: Codex refuses it once that turn ended."""
        if (parsed := _parsed(handle)) is None:
            return False
        thread, turn, _ = parsed
        steering = {"threadId": thread, "expectedTurnId": turn, "input": [{"type": "text", "text": instruction}]}
        try:
            rpc = await self._session()
            await self._call(rpc, "turn/steer", steering)  # refused unless that turn is the one working
            return True
        except (ProviderError, RpcError, Closed, TimeoutError):
            return False

    async def _follow(self, thread: str, turn: str, folder: str, progress: Progress) -> Outcome:
        """Follows the turn in the current session (opened or reopened); `Closed` if it ends meanwhile. `folder`:
        the task's own, the only one its files come back from."""
        rpc = await self._session()
        events = rpc.listen(thread)
        try:
            if thread not in self._joined:  # after a restart, or a lost session: rejoin it, its notifications too
                resumed = await self._call(rpc, "thread/resume", {"threadId": thread, "excludeTurns": True})
                self._loaded.add(thread)
                self._join(rpc, thread)
                found = await self._turn(rpc, thread, turn)
                if found is not None and (outcome := await self._outcome(rpc, found, folder)) is not None:
                    return outcome
                if resumed["thread"]["status"]["type"] != "active":
                    return Outcome.failed("the Codex turn stopped before it ended (its server restarted?)")
            while (event := await events.get()) is not None:
                method, params = event.get("method"), event.get("params") or {}
                if params.get("turnId") == turn and method in ("item/started", "item/completed"):
                    if text := item_step(method, params.get("item") or {}):
                        progress(text)
                elif (
                    method == "turn/completed"
                    and params["turn"]["id"] == turn
                    and (outcome := await self._outcome(rpc, params["turn"], folder)) is not None
                ):
                    return outcome
            raise Closed("the Codex session ended while the turn ran")
        finally:
            rpc.forget(thread)
            self._joined.discard(thread)

    async def _outcome(self, rpc: StdioRpc, turn: Message, folder: str) -> Outcome | None:
        """The outcome of a turn as Codex sums it up (its final answer is in the summary), `None` while it
        runs."""
        match turn["status"]:
            case "completed":
                report = Report.of(final_answer(turn))
                return await report.outcome(folder, lambda path: self._read(rpc, folder, path))
            case "failed":
                error = (turn.get("error") or {}).get("message")
                return Outcome.failed(str(error) if error else "Codex reported the turn as failed")
            case "interrupted":
                return Outcome.stopped()
            case _:
                return None

    async def _turn(self, rpc: StdioRpc, thread: str, turn: str, *, view: str = "summary") -> Message | None:
        listed = await self._call(rpc, "thread/turns/list", {"threadId": thread, "itemsView": view, "limit": 20})
        return next((t for t in listed["data"] if t["id"] == turn), None)

    async def _read(self, rpc: StdioRpc, folder: str, path: str) -> bytes:
        """A file under the task's `folder`, through no link (a link could lead anywhere on that machine), no
        larger than the limit: its size is asked first, as one line of the session carries the whole file."""
        try:
            current, found = posixpath.normpath(folder), {}
            for part in posixpath.relpath(path, current).split("/"):
                current = posixpath.join(current, part)
                found = await self._call(rpc, "fs/getMetadata", {"path": current})
                if found["isSymlink"]:
                    raise Unreadable("a link, not followed")
            if not found.get("isFile"):
                raise Unreadable("not a file")
            counted = await self._call(rpc, "command/exec", {"command": ["wc", "-c", "--", path], "cwd": self._cwd})
            if counted["exitCode"] != 0:
                raise Unreadable(str(counted.get("stderr") or "size unknown").strip())
            if int(counted["stdout"].split()[0]) > self._max_file_bytes:
                raise Unreadable(f"larger than {self._max_file_bytes} bytes")
            return base64.b64decode((await self._call(rpc, "fs/readFile", {"path": path}))["dataBase64"])
        except RpcError as error:
            raise Unreadable(error.message) from None

    async def _session(self) -> StdioRpc:
        """The open session, or a new one: kept only once Codex answered `initialize`."""
        if not self._started:
            raise ContractError(f"{self.name} executor used before start()")
        async with self._opening:
            if self._rpc is not None and self._rpc.alive:
                return self._rpc
            if self._rpc is not None:
                await self._rpc.close()
                self._rpc = None
            rpc = StdioRpc(self._command, self._answer)
            try:
                await rpc.open()
                await self._call(rpc, "initialize", {"clientInfo": {"name": "nestor", "version": __version__}})
                await rpc.notify("initialized")
            except BaseException as error:
                await asyncio.shield(rpc.close())  # never a half-open session, nor its process left behind
                if isinstance(error, Closed | RpcError | TimeoutError):
                    self._unreachable = True
                    raise ProviderError(self.name, f"Codex unreachable: {described(error)}", transient=True) from None
                raise
            self._rpc, self._joined, self._loaded, self._unreachable = rpc, set(), set(), False
            return rpc

    async def _call(self, rpc: StdioRpc, method: str, params: Message) -> Message:
        return await rpc.call(method, params, timeout_s=self._timeout_s)

    def _join(self, rpc: StdioRpc, thread: str) -> None:
        rpc.listen(thread)  # from now on: nothing it says about the thread is missed
        self._joined.add(thread)

    def _thread_settings(self, access: NestorAccess | None, folder: str) -> Message:
        """The thread's settings, working in the task's `folder`; with `access`, Nestor's MCP server among its MCP
        servers, for this thread only."""
        settings: Message = {
            "cwd": folder,
            "sandbox": self._sandbox.value,
            "approvalPolicy": "never",
            "developerInstructions": self._instructions + CODING_REPORT,
        }
        if self._model:
            settings["model"] = self._model
        config = dict(self._config or {})
        if access is not None:
            servers = dict(config.get("mcp_servers") or {})
            servers["nestor"] = {"url": access.url, "http_headers": {"Authorization": f"Bearer {access.key}"}}
            config["mcp_servers"] = servers
        if config:
            settings["config"] = config
        return settings

    async def _answer(self, method: str, params: Message) -> Message:
        if (refusal := DECLINED.get(method)) is None:
            raise RpcError(-32601, f"Nestor does not answer {method}")
        return refusal


def _parsed(ref: str) -> tuple[str, str, str] | None:
    """A task's reference, `thread:turn:folder` (the folder's name under the working directory)."""
    parts = ref.split(":")
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 and all(parts) else None
