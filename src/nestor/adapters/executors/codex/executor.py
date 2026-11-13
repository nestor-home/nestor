"""Codex, through `codex app-server`, running Nestor's tasks."""

import asyncio
import base64
import contextlib
import logging
import posixpath
from collections.abc import Mapping, Sequence
from typing import Any

from nestor import __version__
from nestor.adapters.executors.codex.protocol import COMMAND, DECLINED, ENDED, Sandbox, final_answer, item_step
from nestor.adapters.executors.common import (
    FILES_INSTRUCTIONS,
    INSTRUCTIONS,
    MAX_FILE_BYTES,
    REPORT_SCHEMA,
    Report,
    Unreadable,
    described,
)
from nestor.adapters.executors.jsonrpc import Closed, Message, RpcError, StdioRpc
from nestor.core import ContractError, Health, ProviderError
from nestor.core.i18n import Message as Said
from nestor.modules.cognition import Outcome, Progress, RemoteExecutor

logger = logging.getLogger(__name__)

RECONNECT_S = (1.0, 5.0, 30.0)  # waits before following again a turn whose session was lost


class CodexExecutor(RemoteExecutor):
    """Delegates objectives to Codex; its turns are followed again after a restart.

    `description` states what this Codex can really do (its sandbox, its tools, its MCP servers): the assistant
    promises exactly that. Requests time out after `timeout_s`; a turn itself has no time limit.
    """

    name = "codex"
    brand = "codex"

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

    async def submit(self, objective: str) -> str:
        try:
            rpc = await self._session()
            thread = str((await self._call(rpc, "thread/start", self._thread_settings()))["thread"]["id"])
            self._join(rpc, thread)
            turn = await self._call(
                rpc,
                "turn/start",
                {"threadId": thread, "input": [{"type": "text", "text": objective}], "outputSchema": REPORT_SCHEMA},
            )
            return f"{thread}:{turn['turn']['id']}"
        except (KeyError, TypeError) as error:
            raise ProviderError(self.name, f"unexpected reply from Codex: {error!r}", transient=False) from None
        except RpcError as error:
            raise ProviderError(self.name, f"submission refused: {error}", transient=False) from None
        except (Closed, TimeoutError) as error:
            raise ProviderError(self.name, f"submission failed: {described(error)}", transient=True) from None

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        thread, _, turn = ref.partition(":")
        if not thread or not turn:
            return Outcome.failed(f"not a Codex task reference: {ref!r}")
        waits = iter(self._reconnect_s)
        while True:
            try:
                return await self._follow(thread, turn, progress)
            except (Closed, TimeoutError, ProviderError) as error:  # the session is lost, the turn may go on
                if (wait_s := next(waits, None)) is None:
                    return Outcome.failed(f"lost contact with Codex: {described(error)}")
                logger.warning("%s: lost contact with Codex, following again in %ss (%s)", self.name, wait_s, error)
                await asyncio.sleep(wait_s)
            except RpcError as error:
                return Outcome.failed(f"Codex refused: {error}")
            except (KeyError, TypeError, ValueError) as error:  # not the protocol: a missing field, bad base64
                return Outcome.failed(f"unexpected reply from Codex: {error!r}")

    async def stop(self, ref: str) -> bool:
        thread, _, turn = ref.partition(":")
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

    async def _follow(self, thread: str, turn: str, progress: Progress) -> Outcome:
        """Follows the turn in the current session (opened or reopened); `Closed` if it ends meanwhile."""
        rpc = await self._session()
        events = rpc.listen(thread)
        try:
            if thread not in self._joined:  # after a restart, or a lost session: rejoin it, its notifications too
                resumed = await self._call(rpc, "thread/resume", {"threadId": thread, "excludeTurns": True})
                self._join(rpc, thread)
                found = await self._turn(rpc, thread, turn)
                if found is not None and (outcome := await self._outcome(rpc, found)) is not None:
                    return outcome
                if resumed["thread"]["status"]["type"] != "active":
                    return Outcome.failed("the Codex turn stopped before it ended (its server restarted?)")
            while (event := await events.get()) is not None:
                params = event.get("params") or {}
                if params.get("turnId") == turn and event.get("method") == "item/started":
                    if text := item_step(params.get("item") or {}):
                        progress(text)
                elif (
                    event.get("method") == "turn/completed"
                    and params["turn"]["id"] == turn
                    and (outcome := await self._outcome(rpc, params["turn"])) is not None
                ):
                    return outcome
            raise Closed("the Codex session ended while the turn ran")
        finally:
            rpc.forget(thread)
            self._joined.discard(thread)

    async def _outcome(self, rpc: StdioRpc, turn: Message) -> Outcome | None:
        """The outcome of a turn as Codex sums it up (its final answer is in the summary), `None` while it runs."""
        match turn["status"]:
            case "completed":
                return await Report.of(final_answer(turn)).outcome(self._cwd, lambda path: self._read(rpc, path))
            case "failed":
                error = (turn.get("error") or {}).get("message")
                return Outcome.failed(str(error) if error else "Codex reported the turn as failed")
            case "interrupted":
                return Outcome.cancelled()
            case _:
                return None

    async def _turn(self, rpc: StdioRpc, thread: str, turn: str, *, view: str = "summary") -> Message | None:
        listed = await self._call(rpc, "thread/turns/list", {"threadId": thread, "itemsView": view, "limit": 20})
        return next((t for t in listed["data"] if t["id"] == turn), None)

    async def _read(self, rpc: StdioRpc, path: str) -> bytes:
        """A file under the working directory, through no link (a link could lead anywhere on that machine), no
        larger than the limit: its size is asked first, as one line of the session carries the whole file."""
        try:
            current, found = posixpath.normpath(self._cwd), {}
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
            self._rpc, self._joined, self._unreachable = rpc, set(), False
            return rpc

    async def _call(self, rpc: StdioRpc, method: str, params: Message) -> Message:
        return await rpc.call(method, params, timeout_s=self._timeout_s)

    def _join(self, rpc: StdioRpc, thread: str) -> None:
        rpc.listen(thread)  # from now on: nothing it says about the thread is missed
        self._joined.add(thread)

    def _thread_settings(self) -> Message:
        settings: Message = {
            "cwd": self._cwd,
            "sandbox": self._sandbox.value,
            "approvalPolicy": "never",
            "developerInstructions": self._instructions + FILES_INSTRUCTIONS,
        }
        if self._model:
            settings["model"] = self._model
        if self._config:
            settings["config"] = dict(self._config)
        return settings

    async def _answer(self, method: str, params: Message) -> Message:
        if (refusal := DECLINED.get(method)) is None:
            raise RpcError(-32601, f"Nestor does not answer {method}")
        return refusal
