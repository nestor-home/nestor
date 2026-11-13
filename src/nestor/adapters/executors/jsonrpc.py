"""JSON-RPC over a child process's standard input and output, one JSON object per line: the wire of
`codex app-server`, whether it runs here or behind a command that relays it (`ssh host codex app-server proxy`).

Codex leaves out the `jsonrpc` version field; requests go both ways. Notifications are routed by the thread they
name (`params.threadId`) to whoever listens for it; the others are dropped. When the process ends, every pending
call fails with `Closed` and every listener receives `None`.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from nestor.adapters.executors.process import Child

logger = logging.getLogger(__name__)

STOP_TIMEOUT_S = 5.0
ENDING_S = 1.0

type Message = dict[str, Any]
type Answer = Callable[[str, Message], Awaitable[Message]]


class RpcError(Exception):
    """The other side answered a request with an error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{message} ({code})")
        self.code, self.message = code, message


class Closed(Exception):
    """The process ended, or could not start."""


class StdioRpc:
    """One child process and its JSON-RPC session. `answer` replies to the requests the process sends (it raises
    `RpcError` to refuse one)."""

    def __init__(self, command: Sequence[str], answer: Answer) -> None:
        self._command, self._answer = list(command), answer
        self._child: Child | None = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Message]] = {}
        self._listeners: dict[str, asyncio.Queue[Message | None]] = {}
        self._next_id = 0

    @property
    def alive(self) -> bool:
        return self._reader is not None and not self._reader.done()

    async def open(self) -> None:
        try:
            self._child = await Child.start(self._command)
        except OSError as error:
            raise Closed(f"{self._command[0]} could not start: {error.strerror or error}") from None
        self._reader = asyncio.create_task(self._read(self._child), name=f"{self._command[0]} rpc")

    async def call(self, method: str, params: Message, *, timeout_s: float) -> Message:
        """The result of `method`; `RpcError` if refused, `Closed` if the process ends, `TimeoutError`."""
        self._next_id += 1
        request_id = self._next_id
        reply: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = reply
        try:
            await self._send({"id": request_id, "method": method, "params": params})
            async with asyncio.timeout(timeout_s):
                return await reply
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str) -> None:
        await self._send({"method": method})

    def listen(self, thread: str) -> "asyncio.Queue[Message | None]":
        """The notifications about `thread` from now on (the same queue for every caller), `None` once closed."""
        if thread not in self._listeners:
            self._listeners[thread] = asyncio.Queue()
            if not self.alive:
                self._listeners[thread].put_nowait(None)
        return self._listeners[thread]

    def forget(self, thread: str) -> None:
        self._listeners.pop(thread, None)

    async def close(self) -> None:
        child, self._child = self._child, None
        if child is not None:
            await child.stop(STOP_TIMEOUT_S)
        if self._reader is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader

    async def _send(self, message: Message) -> None:
        child = self._child
        if child is None or child.process.stdin is None or not self.alive:
            raise Closed(child.ended() if child else f"{self._command[0]} is not running")
        try:
            child.process.stdin.write(json.dumps(message).encode() + b"\n")
            await child.process.stdin.drain()
        except (ConnectionError, RuntimeError) as error:
            raise Closed(child.ended()) from error

    async def _read(self, child: Child) -> None:
        try:
            async for line in child.lines():
                try:
                    message = json.loads(line)
                except ValueError:
                    logger.warning("%s: a line that is not JSON was skipped", self._command[0])
                    continue
                if isinstance(message, dict):
                    await self._dispatch(message)
        finally:
            with contextlib.suppress(TimeoutError):  # its last words on stderr say why it ended
                await asyncio.wait_for(asyncio.shield(child.wait()), ENDING_S)
            ended = Closed(child.ended())
            for reply in self._pending.values():
                if not reply.done():
                    reply.set_exception(ended)
            for queue in self._listeners.values():
                queue.put_nowait(None)

    async def _dispatch(self, message: Message) -> None:
        if "method" not in message:
            reply = self._pending.get(message.get("id"))
            if reply is not None and not reply.done():
                if isinstance(error := message.get("error"), dict):
                    reply.set_exception(RpcError(int(error.get("code", 0)), str(error.get("message", ""))))
                else:
                    reply.set_result(message.get("result") or {})
            return
        params: Message = message["params"] if isinstance(message.get("params"), dict) else {}
        if "id" in message:
            await self._reply(message["id"], str(message["method"]), params)
        elif (queue := self._listeners.get(str(params.get("threadId")))) is not None:
            queue.put_nowait(message)

    async def _reply(self, request_id: object, method: str, params: Message) -> None:
        try:
            answer: Message = {"id": request_id, "result": await self._answer(method, params)}
        except RpcError as error:
            answer = {"id": request_id, "error": {"code": error.code, "message": error.message}}
        with contextlib.suppress(Closed):
            await self._send(answer)
