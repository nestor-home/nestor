"""A fake `codex app-server`, as observed on codex-cli 0.160.0: JSON-RPC without the version field, one object per
line, threads and turns, item and turn notifications, approval requests, files read back in base64.

It plays the Codex daemon a relay reaches (`codex app-server proxy`): its threads outlive the sessions, so a new
executor plays a Nestor restart. With `daemon=False` it plays a local `codex app-server` instead, whose running turn
dies with the session that started it."""

import asyncio
import base64
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from nestor.adapters.executors.codex import CodexExecutor

RELAY = Path(__file__).with_name("relay.py")
CWD = "/srv/codex/work"
REPORT = {"report": "C'est fait.", "files": []}
ITEMS = (  # what a turn does, as `item/started` says it
    {"type": "userMessage", "id": "u1", "content": []},
    {"type": "reasoning", "id": "r1"},
    {"type": "commandExecution", "id": "exec-1", "command": "/bin/bash -lc 'ls'", "status": "inProgress"},
    {"type": "fileChange", "id": "f1", "changes": [{"path": "src/a.py", "kind": {"type": "update"}, "diff": ""}]},
    {"type": "mcpToolCall", "id": "t1", "server": "nestor", "tool": "read_result", "status": "inProgress"},
    {"type": "webSearch", "id": "w1", "query": "pytest asyncio"},
    {"type": "imageGeneration", "id": "i1", "status": "inProgress", "result": ""},
)


@dataclass(slots=True)
class FakeTurn:
    id: str
    objective: str
    status: str = "inProgress"
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def wire(self) -> dict[str, Any]:
        error = {"message": self.error} if self.error else None
        return {"id": self.id, "items": self.items, "itemsView": "full", "status": self.status, "error": error}


@dataclass(slots=True)
class FakeThread:
    id: str
    settings: dict[str, Any]
    turns: list[FakeTurn] = field(default_factory=list)
    owner: object = None  # the session running it, for a local server


class FakeCodex:
    """`holds`: turns run until `finish`; `fails`: they fail; `confirms_stop`: an interrupt stops the turn;
    `asks`: the turn sends this approval request first and keeps the answer in `answers`; `files`: what the
    filesystem holds; `report`: the final answer; `refuses`: no thread starts; `garbled`: threads come back in
    another shape; `hangs_up`: the session ends as a thread is asked for; `lags`: the history still reads a
    finished turn as running; `links`: symbolic links of the filesystem, to the paths they lead to."""

    def __init__(
        self,
        *,
        holds: bool = False,
        fails: bool = False,
        confirms_stop: bool = True,
        daemon: bool = True,
        asks: str | None = None,
        files: dict[str, bytes] | None = None,
        report: object = None,
        refuses: bool = False,
        garbled: bool = False,
        hangs_up: bool = False,
        lags: bool = False,
        links: dict[str, str] | None = None,
    ) -> None:
        self.holds, self.fails, self.confirms_stop, self.daemon, self.asks = holds, fails, confirms_stop, daemon, asks
        self.files, self.refuses, self.garbled, self.hangs_up = files or {}, refuses, garbled, hangs_up
        self.lags, self.links = lags, links or {}
        self.report = REPORT if report is None else report
        self.threads: dict[str, FakeThread] = {}
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.answers: list[dict[str, Any]] = []
        self._subscribers: dict[str, set[asyncio.StreamWriter]] = {}
        self._sessions: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None
        self._count = 0
        self._asked: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def __aenter__(self) -> Self:
        self._server = await asyncio.start_server(self._session, "127.0.0.1", 0, limit=2**26)
        return self

    async def __aexit__(self, *_: type[BaseException] | BaseException | TracebackType | None) -> None:
        assert self._server is not None
        for writer in self._sessions:
            writer.close()
        self._server.close()

    def command(self) -> list[str]:
        assert self._server is not None
        return [sys.executable, str(RELAY), str(self._server.sockets[0].getsockname()[1])]

    def executor(self, **options: Any) -> CodexExecutor:
        options.setdefault("working_directory", CWD)
        options.setdefault("description", "write and run code")
        options.setdefault("poll_interval_s", 0.01)
        options.setdefault("command", self.command())
        return CodexExecutor(**options)

    def turn(self, ref: str) -> FakeTurn:
        thread, _, turn = ref.partition(":")
        return next(t for t in self.threads[thread].turns if t.id == turn)

    async def finish(self, ref: str, *, report: object = None) -> None:
        thread, _, _ = ref.partition(":")
        self._complete(self.threads[thread], self.turn(ref), report or self.report)

    def drop_sessions(self) -> None:
        """The relay's connections break: every session ends at once."""
        for writer in list(self._sessions):
            writer.close()

    def go_away(self) -> None:
        """The server stops: no session reaches it any more."""
        assert self._server is not None
        self._server.close()
        self.drop_sessions()

    async def _session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._sessions.add(writer)
        try:
            while line := await reader.readline():
                message = json.loads(line)
                if "method" not in message:
                    self._asked.pop(message["id"]).set_result(message)
                elif "id" in message:
                    handling = asyncio.create_task(self._handle(writer, message))
                    self._tasks.add(handling)
                    handling.add_done_callback(self._tasks.discard)
        except ConnectionError:
            pass
        finally:
            self._sessions.discard(writer)
            for subscribers in self._subscribers.values():
                subscribers.discard(writer)
            if not self.daemon:  # a local server stops with its session: its running turns stop there
                for thread in self.threads.values():
                    if thread.owner is writer:
                        thread.owner = None

    async def _handle(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        method, params = message["method"], message.get("params") or {}
        self.requests.append((method, params))
        try:
            reply = {"id": message["id"], "result": await self._result(writer, method, params)}
        except _Refused as refused:
            reply = {"id": message["id"], "error": {"code": refused.code, "message": refused.message}}
        self._write(writer, reply)

    async def _result(self, writer: asyncio.StreamWriter, method: str, params: dict[str, Any]) -> dict[str, Any]:
        match method:
            case "initialize":
                return {"userAgent": "codex/0.160.0", "codexHome": "/srv/codex/.codex", "platformOs": "linux"}
            case "thread/start" if self.hangs_up:
                writer.close()
                return {}
            case "thread/start" | "thread/resume" if self.garbled:
                return {"thread": None}
            case "thread/turns/list" if self.garbled:
                return {"data": None}
            case "thread/start":
                if self.refuses:
                    raise _Refused(-32600, "cwd is not a directory")
                thread = FakeThread(self._id("thread"), params, owner=writer)
                self.threads[thread.id] = thread
                self._subscribers.setdefault(thread.id, set()).add(writer)
                return {"thread": self._thread(thread)}
            case "thread/resume":
                thread = self._thread_of(params)
                self._subscribers.setdefault(thread.id, set()).add(writer)
                return {"thread": self._thread(thread)}
            case "turn/start":
                thread = self._thread_of(params)
                turn = FakeTurn(self._id("turn"), params["input"][0]["text"])
                thread.turns.append(turn)
                running = asyncio.create_task(self._run(writer, thread, turn))  # after this reply: no await before it
                self._tasks.add(running)
                running.add_done_callback(self._tasks.discard)
                return {"turn": {"id": turn.id, "items": [], "itemsView": "notLoaded", "status": "inProgress"}}
            case "turn/interrupt":
                thread = self._thread_of(params)
                turn = next((t for t in thread.turns if t.id == params["turnId"] and t.status == "inProgress"), None)
                if turn is None or (not self.daemon and thread.owner is None):
                    raise _Refused(-32600, "no active turn to interrupt")
                if self.confirms_stop:
                    turn.status = "interrupted"
                    self._notify(thread, "turn/completed", {"threadId": thread.id, "turn": turn.wire()})
                return {}
            case "thread/turns/list":
                thread = self._thread_of(params)
                turns = [t.wire() for t in reversed(thread.turns)]
                if self.lags:  # its history is written after the notification
                    turns = [{**t, "status": "inProgress", "items": []} for t in turns]
                return {"data": turns, "nextCursor": None}
            case "fs/getMetadata":
                path = params["path"]
                target = self.links.get(path, path)
                if target in self.files:
                    return {"isFile": True, "isDirectory": False, "isSymlink": path in self.links}
                if any(f.startswith(target + "/") for f in self.files):
                    return {"isFile": False, "isDirectory": True, "isSymlink": path in self.links}
                raise _Refused(-32603, "No such file or directory (os error 2)")
            case "command/exec" if params["command"][:3] == ["wc", "-c", "--"]:
                path = self.links.get(params["command"][3], params["command"][3])
                if path not in self.files or path.endswith("locked.txt"):
                    return {"exitCode": 1, "stdout": "", "stderr": f"wc: {path}: open: No such file or directory\n"}
                return {"exitCode": 0, "stdout": f"  {len(self.files[path])} {path}\n", "stderr": ""}
            case "fs/readFile":
                path = self.links.get(params["path"], params["path"])
                return {"dataBase64": base64.b64encode(self.files[path]).decode()}
            case _:
                raise _Refused(-32601, f"unknown method {method}")

    async def _run(self, writer: asyncio.StreamWriter, thread: FakeThread, turn: FakeTurn) -> None:
        self._notify(thread, "turn/started", {"threadId": thread.id, "turn": turn.wire()})
        for item in ITEMS:
            self._notify(thread, "item/started", {"threadId": thread.id, "turnId": turn.id, "item": item})
        if self.asks:
            self._count += 1
            asked = self._asked[self._count] = asyncio.get_running_loop().create_future()
            question = {"threadId": thread.id, "turnId": turn.id, "itemId": "exec-1", "command": "rm -rf /"}
            self._write(writer, {"id": self._count, "method": self.asks, "params": question})
            self.answers.append(await asked)
        if not self.holds:
            self._complete(thread, turn, self.report)

    def _complete(self, thread: FakeThread, turn: FakeTurn, report: object) -> None:
        if self.fails:
            turn.status, turn.error = "failed", "the model refused"
        else:
            text = report if isinstance(report, str) else json.dumps(report)
            turn.items.append({"type": "agentMessage", "id": "m1", "text": "Je regarde.", "phase": "commentary"})
            turn.items.append({"type": "agentMessage", "id": "m2", "text": text, "phase": "final_answer"})
            turn.status = "completed"
        self._notify(thread, "turn/completed", {"threadId": thread.id, "turn": {**turn.wire(), "itemsView": "summary"}})

    def _thread(self, thread: FakeThread) -> dict[str, Any]:
        running = any(t.status == "inProgress" for t in thread.turns) and (self.daemon or thread.owner is not None)
        return {"id": thread.id, "cwd": thread.settings.get("cwd"), "status": {"type": "active" if running else "idle"}}

    def _thread_of(self, params: dict[str, Any]) -> FakeThread:
        if (thread := self.threads.get(params["threadId"])) is None:
            raise _Refused(-32600, f"invalid thread id: {params['threadId']}")
        return thread

    def _notify(self, thread: FakeThread, method: str, params: dict[str, Any]) -> None:
        for writer in self._subscribers.get(thread.id, ()):
            self._write(writer, {"method": method, "params": params})

    def _write(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        if not writer.is_closing():
            writer.write(json.dumps(message).encode() + b"\n")

    def _id(self, kind: str) -> str:
        self._count += 1
        return f"{kind}-{self._count:04d}"


class _Refused(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code, self.message = code, message
