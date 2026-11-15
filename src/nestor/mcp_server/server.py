"""Nestor's MCP server for executors, on the admin's address at `/mcp`: what an executor reaches while it works on a
task (its brief, the requester's memory, questions to them, its progress, its files).

Every call carries the executor's key (`Authorization: Bearer nstx_…`) and the task's capability (`task`, `nstt_…`):
the key says who calls, the capability what for. A tool runs only when both match a task of that executor that is
still running; otherwise every refusal reads the same. Calls are limited per key, and each is journaled
(`ExecutorCalled`); what a tool does is journaled by its module, as when the agent does it.
"""

import asyncio
import base64
import logging
import time
from collections import deque
from collections.abc import Callable, MutableMapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings

from nestor import __version__
from nestor.core import PersonId
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.delegation import ExecutorKeys
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.cognition.tools import ToolFailed
from nestor.modules.conversation import Attached, NotificationTurn, UserTurn
from nestor.modules.conversation.history import in_conversation
from nestor.modules.initiative import QuestionState
from nestor.modules.memory.episodes.transcript import transcript
from nestor.runtime import Nestor

log = logging.getLogger(__name__)

SCOPE_KEY = "nestor.executor"  # the executor a request's key belongs to, set before the MCP app sees it
REFUSED = "not a running task of yours"  # whatever is wrong: the key, the task, its executor, its end
CALLS_PER_MINUTE = 120  # per key
FILE_BYTES = 20_000_000  # largest file read or handed back through the server
BODY_BYTES = FILE_BYTES * 4 // 3 + 1_000_000  # a request carrying such a file in base64
BRIEF_LINES = 40  # of the conversation the task came from
DESCRIPTIONS = {  # what the executor's model reads of each tool
    "task_brief": (
        "What the task is: its objective, who asked, when and where, the conversation it came from, and the "
        "files they sent (read one with read_file)."
    ),
    "read_file": "The content of a file sent with the task, by its `file` from task_brief, base64.",
    "recall": (
        "What Nestor knows of the requester: their memories matching `query`, and their past conversations "
        "(dated: since and until as 2026-11-01)."
    ),
    "remember": "Keep a lasting fact about the requester, learned while working on the task.",
    "report_progress": "Say what you are doing now, in a few words: the requester and Nestor see it.",
    "ask_requester": (
        "Ask the requester a question; it returns at once with the question's id: call check_answer later for"
        " their answer."
    ),
    "check_answer": "The requester's answer to a question asked with ask_requester, once they gave it.",
    "attach_file": "Hand a file you made back with the task's result (base64, at most 20 MB).",
    "home_state": "Who is home now, and the occupied rooms, as the home system sees it.",
}
INSTRUCTIONS = """Tools for the task Nestor, the household assistant, handed you. Every tool takes `task`, the value \
your brief gives. Start with task_brief."""


@dataclass(frozen=True, slots=True)
class Sent:
    """The conversation a task was handed over in, until then."""

    since: datetime  # when it started
    files: tuple[Attached, ...]  # what people sent in it


class ExecutorServer:
    """The MCP server and the ASGI endpoint the admin serves it at, while `running()`."""

    def __init__(self, nestor: Nestor, keys: ExecutorKeys) -> None:
        self._nestor, self._keys = nestor, keys
        self._calls: dict[str, deque[float]] = {}
        self._sent: dict[str, Sent] = {}  # by task: what was said and sent before it, read once
        self.mcp = MCPServer("nestor", instructions=INSTRUCTIONS, version=__version__)
        self._register()
        # makes its session manager: reached at the admin's public address (not only localhost, which the SDK's
        # rebinding guard would require: every call is authenticated by its key), with bodies big enough for a file
        self.mcp.streamable_http_app(
            stateless_http=True,
            json_response=True,
            max_request_body_size=BODY_BYTES,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        self.endpoint = _Guarded(StreamableHTTPASGIApp(self.mcp.session_manager), self._caller, self._within_rate)

    def running(self) -> AbstractAsyncContextManager[None]:
        """While it serves: the SDK's session manager, which runs once."""
        return self.mcp.session_manager.run()

    def _caller(self, key: str) -> str | None:
        """The executor a key belongs to; `None` for a key that is no executor's."""
        return self._keys.caller(key)

    def _within_rate(self, executor: str) -> bool:
        now, calls = time.monotonic(), self._calls.setdefault(executor, deque())
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= CALLS_PER_MINUTE:
            log.warning("executor %s calls Nestor's MCP server too often", executor)
            return False
        calls.append(now)
        return True

    async def _task(self, ctx: Context, task: str, tool: str) -> Task:
        request = ctx.request_context.request
        assert request is not None  # served over HTTP, behind `_Guarded`, which named the executor
        found = await self._nestor.tasks.admit(request.scope[SCOPE_KEY], task, tool)
        if found is None:
            raise ToolError(REFUSED)
        return found

    def _requester(self, task: Task) -> PersonId:
        if task.requested_by is None:
            raise ToolError("nobody asked for this task: nothing of anyone's to read, keep or ask")
        return task.requested_by

    async def _before(self, task: Task) -> Sent:
        """The conversation the task was handed over in, until then: when it started and the files sent in it."""
        if (known := self._sent.get(task.id)) is not None:
            return known
        opened: list[UserTurn | NotificationTurn] = []  # what opened its turns: a person, or Nestor (a wake-up)
        if task.exchange is not None:
            history = await self._nestor.journal.history(UserTurn, NotificationTurn, session=task.origin.session)
            opened = [t for t in in_conversation(history, task.exchange.conversation_id) if t.at <= task.started_at]
        found = Sent(
            since=opened[0].at if opened else task.started_at,
            files=tuple(a for turn in opened if isinstance(turn, UserTurn) for a in turn.attachments),
        )
        running = {t.id for t in self._nestor.tasks.running()}
        self._sent = {k: v for k, v in self._sent.items() if k in running} | {task.id: found}  # ended tasks go
        return found

    def _register(self) -> None:
        nestor = self._nestor
        memory = nestor.memory_tools

        @self.mcp.tool(description=DESCRIPTIONS["task_brief"])
        async def task_brief(task: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "task_brief")
            zone = ZoneInfo(nestor.config.persona.timezone)
            requester = nestor.household.person(found.requested_by) if found.requested_by else None
            before = await self._before(found)
            conversation = (
                await transcript(
                    nestor.journal,
                    nestor.household,
                    address=found.origin,
                    conversation=found.exchange.conversation_id,
                    since=before.since,
                    assistant=nestor.config.persona.name,
                    timezone=nestor.config.persona.timezone,
                )
                if found.exchange is not None
                else []
            )
            return {
                "objective": found.objective,
                "requested_by": requester.name if requester else None,
                "asked_at": f"{found.started_at.astimezone(zone):%A %d %B %Y %H:%M} ({nestor.config.persona.timezone})",
                "channel": found.origin.channel,
                "conversation": conversation[-BRIEF_LINES:],
                "files": [
                    {"file": a.blob.digest, "name": a.name, "media_type": a.blob.media_type, "bytes": a.blob.size}
                    for a in before.files
                ],
            }

        @self.mcp.tool(description=DESCRIPTIONS["read_file"])
        async def read_file(task: str, file: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "read_file")
            sent = next((a for a in (await self._before(found)).files if a.blob.digest == file), None)
            if sent is None:
                raise ToolError(f"no file {file} was sent with this task")
            if sent.blob.size > FILE_BYTES:
                raise ToolError(f"{sent.name or file} is larger than {FILE_BYTES // 1_000_000} MB")
            data = await nestor.blobs.get(file)
            encoded = await asyncio.to_thread(base64.b64encode, data)  # up to 27 MB of text: off the loop
            return {"name": sent.name, "media_type": sent.blob.media_type, "base64": encoded.decode()}

        @self.mcp.tool(description=DESCRIPTIONS["recall"])
        async def recall(task: str, query: str, ctx: Context, since: str = "", until: str = "") -> dict[str, object]:
            requester = self._requester(await self._task(ctx, task, "recall"))
            try:
                found = await memory.search(
                    query,
                    person=requester,
                    about=requester,  # what is theirs, never another person's nor the household's
                    since=memory.bound(since, end=False),
                    until=memory.bound(until, end=True),
                )
            except ToolFailed as failed:
                raise ToolError(str(failed)) from None
            return dict(found)

        @self.mcp.tool(description=DESCRIPTIONS["remember"])
        async def remember(task: str, fact: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "remember")
            kept = await memory.keep(fact, about=self._requester(found), source=found.origin, exchange=found.exchange)
            return dict(kept)

        @self.mcp.tool(description=DESCRIPTIONS["report_progress"])
        async def report_progress(task: str, step: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "report_progress")
            nestor.tasks.report(found, step.strip()[:500])
            return {"status": "noted"}

        @self.mcp.tool(description=DESCRIPTIONS["ask_requester"])
        async def ask_requester(task: str, question: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "ask_requester")
            asked = await nestor.message_book.request(
                self._requester(found),
                f'{found.executor}, working on "{found.objective[:160]}": {question}',
                requested_by=None,
                origin=found.origin,
                expects_reply=True,
                exchange=found.exchange,
                task=found.id,
            )
            return {"question": asked.message_id, "status": "asked"}

        @self.mcp.tool(description=DESCRIPTIONS["check_answer"])
        async def check_answer(task: str, question: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "check_answer")
            book = nestor.message_book
            asked = book.get(question)
            if asked is None or asked.task != found.id:
                raise ToolError(f"no question {question} from this task")
            state = book.state(question)
            if state is QuestionState.ANSWERED:
                return {"status": "answered", "answer": book.answer_to(question)}
            if state is QuestionState.UNDELIVERED:
                return {"status": "not delivered", "note": "it could not reach them; go on without it or say so"}
            return {"status": "waiting"}

        @self.mcp.tool(description=DESCRIPTIONS["attach_file"])
        async def attach_file(task: str, name: str, media_type: str, content: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "attach_file")
            try:
                data = await asyncio.to_thread(base64.b64decode, content, validate=True)  # off the loop
            except ValueError:
                raise ToolError("content must be base64") from None
            if len(data) > FILE_BYTES:
                raise ToolError(f"larger than {FILE_BYTES // 1_000_000} MB")
            made = Attachment(kind=AttachmentKind.of(media_type), data=data, media_type=media_type, name=name)
            kept = await nestor.tasks.add_file(found, made)
            return {"status": "attached", "file": kept.digest}

        if nestor.presence is not None:
            presence_source = nestor.presence

            @self.mcp.tool(description=DESCRIPTIONS["home_state"])
            async def home_state(task: str, ctx: Context) -> dict[str, object]:
                await self._task(ctx, task, "home_state")
                presence = presence_source.presence()
                people = {
                    nestor.household.person(person).name: (
                        "unknown" if where.home is None else (where.room or "home") if where.home else "away"
                    )
                    for person, where in presence.people.items()
                }
                return {"people": people, "occupied_rooms": sorted(presence.occupied_rooms)}


class _Guarded:
    """The MCP endpoint behind the executor's key: a request without a key that belongs to an executor is refused
    (401), one over its rate held back (429), before the MCP app sees either."""

    def __init__(
        self, app: StreamableHTTPASGIApp, caller: Callable[[str], str | None], within_rate: Callable[[str], bool]
    ) -> None:
        self._app, self._caller, self._within_rate = app, caller, within_rate

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        headers = dict(scope.get("headers") or ())
        scheme, _, key = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
        executor = self._caller(key.strip()) if scheme.lower() == "bearer" and key.strip() else None
        if executor is None:
            await _refuse(send, 401, b"unauthorized", (b"www-authenticate", b'Bearer realm="nestor"'))
            return
        if not self._within_rate(executor):
            await _refuse(send, 429, b"too many calls", (b"retry-after", b"60"))
            return
        scope[SCOPE_KEY] = executor
        await self._app(scope, receive, send)


async def _refuse(send: Any, status: int, body: bytes, header: tuple[bytes, bytes]) -> None:
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"text/plain"), header]})
    await send({"type": "http.response.body", "body": body})
