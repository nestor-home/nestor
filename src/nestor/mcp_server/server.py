"""Nestor's MCP server for executors, on the admin's address at `/mcp`: what an executor reaches while it works on a
task (its brief, the requester's memory, questions to them, its progress, its files).

Every call carries the executor's key (`Authorization: Bearer nstx_…`) and the task's capability (`task`, `nstt_…`):
the key says who calls, the capability what for. A tool runs only when both match a task of that executor that is
still running; otherwise every refusal reads the same. Calls are limited per key, and each is journaled
(`ExecutorCalled`); what a tool does is journaled by its module, as when the agent does it.
"""

import base64
import logging
import time
from collections import deque
from collections.abc import Callable, Mapping, MutableMapping
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager

from nestor import __version__
from nestor.core import ContractError
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.delegation import ExecutorCalled
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.conversation import UserTurn
from nestor.modules.identity import Speaker
from nestor.modules.memory.episodes.transcript import transcript
from nestor.runtime import Nestor

log = logging.getLogger(__name__)

SCOPE_KEY = "nestor.executor"  # the executor a request's key belongs to, set before the MCP app sees it
REFUSED = "not a running task of yours"  # whatever is wrong: the key, the task, its executor, its end
CALLS_PER_MINUTE = 120  # per key
FILE_BYTES = 20_000_000  # largest file read or handed back through the server
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


class ExecutorServer:
    """The MCP server and the ASGI endpoint the admin serves it at; `running()` while the admin serves."""

    def __init__(self, nestor: Nestor) -> None:
        if nestor.executor_keys is None:
            raise ContractError("executors reach Nestor only where the admin has a public_url and a vault")
        self._nestor, self._keys = nestor, nestor.executor_keys
        self._calls: dict[str, deque[float]] = {}
        self.mcp = MCPServer("nestor", instructions=INSTRUCTIONS, version=__version__)
        self._register()
        self.mcp.streamable_http_app(stateless_http=True, json_response=True)  # makes its session manager
        self.endpoint = _Guarded(StreamableHTTPASGIApp(self.mcp.session_manager), self._caller)

    @property
    def sessions(self) -> StreamableHTTPSessionManager:
        return self.mcp.session_manager

    def _caller(self, key: str) -> str | None:
        """The executor a key belongs to, within its rate; `None` refuses the request."""
        executor = self._keys.caller(key)
        if executor is None:
            return None
        now, calls = time.monotonic(), self._calls.setdefault(executor, deque())
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= CALLS_PER_MINUTE:
            log.warning("executor %s calls Nestor's MCP server too often", executor)
            return None
        calls.append(now)
        return executor

    async def _task(self, ctx: Context, task: str, tool: str) -> Task:
        request = ctx.request_context.request
        executor = request.scope.get(SCOPE_KEY) if request is not None else None
        found = self._nestor.tasks.assigned(executor, task) if executor else None
        await self._nestor.journal.publish(
            ExecutorCalled(
                source="mcp",
                session=found.origin.session if found else None,
                executor=executor or "",
                task_id=found.id if found else None,
                tool=tool,
                ok=found is not None,
            )
        )
        if found is None:
            raise ToolError(REFUSED)
        return found

    def _context(self, task: Task) -> ToolContext:
        """The requester's own context, for the agent's tools run on the task's behalf: what is theirs, nothing more."""
        if task.requested_by is None:
            raise ToolError("nobody asked for this task: nothing of anyone's to read or keep")
        return ToolContext(address=task.origin, speaker=Speaker.account(task.requested_by), exchange=task.exchange)

    def _register(self) -> None:
        nestor = self._nestor

        @self.mcp.tool(description=DESCRIPTIONS["task_brief"])
        async def task_brief(task: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "task_brief")
            zone = ZoneInfo(nestor.config.persona.timezone)
            requester = nestor.household.person(found.requested_by) if found.requested_by else None
            conversation: list[str] = []
            files: list[dict[str, object]] = []
            if found.exchange is not None:
                since = found.started_at - timedelta(hours=4)
                conversation = (
                    await transcript(
                        nestor.journal,
                        nestor.household,
                        address=found.origin,
                        conversation=found.exchange.conversation_id,
                        since=since,
                        assistant=nestor.config.persona.name,
                        timezone=nestor.config.persona.timezone,
                    )
                )[-BRIEF_LINES:]
                files = [
                    {"file": a.blob.digest, "name": a.name, "media_type": a.blob.media_type, "bytes": a.blob.size}
                    for a in await self._sent(found)
                ]
            return {
                "objective": found.objective,
                "requested_by": requester.name if requester else None,
                "asked_at": f"{found.started_at.astimezone(zone):%A %d %B %Y %H:%M} ({nestor.config.persona.timezone})",
                "channel": found.origin.channel,
                "conversation": conversation,
                "files": files,
            }

        @self.mcp.tool(description=DESCRIPTIONS["read_file"])
        async def read_file(task: str, file: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "read_file")
            sent = next((a for a in await self._sent(found) if a.blob.digest == file), None)
            if sent is None:
                raise ToolError(f"no file {file} was sent with this task")
            if sent.blob.size > FILE_BYTES:
                raise ToolError(f"{sent.name or file} is larger than {FILE_BYTES // 1_000_000} MB")
            data = await nestor.blobs.get(file)
            return {"name": sent.name, "media_type": sent.blob.media_type, "base64": base64.b64encode(data).decode()}

        @self.mcp.tool(description=DESCRIPTIONS["recall"])
        async def recall(task: str, query: str, ctx: Context, since: str = "", until: str = "") -> dict[str, object]:
            found = await self._task(ctx, task, "recall")
            context = self._context(found)
            arguments = {"query": query, "about": str(found.requested_by), "since": since, "until": until}
            return dict(await self._run_memory("recall", {k: v for k, v in arguments.items() if v}, context))

        @self.mcp.tool(description=DESCRIPTIONS["remember"])
        async def remember(task: str, fact: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "remember")
            return dict(
                await self._run_memory(
                    "remember", {"text": fact, "about": str(found.requested_by)}, self._context(found)
                )
            )

        @self.mcp.tool(description=DESCRIPTIONS["report_progress"])
        async def report_progress(task: str, step: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "report_progress")
            nestor.tasks.report(found, step.strip()[:500])
            return {"status": "noted"}

        @self.mcp.tool(description=DESCRIPTIONS["ask_requester"])
        async def ask_requester(task: str, question: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "ask_requester")
            if found.requested_by is None:
                raise ToolError("nobody asked for this task: there is no one to ask")
            asked = await nestor.message_book.request(
                found.requested_by,
                f"{found.executor}, working on the task you handed over ({found.objective[:160]}), asks: {question}",
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
            asked = nestor.message_book.get(question)
            if asked is None or asked.task != found.id:
                raise ToolError(f"no question {question} from this task")
            if (answer := nestor.message_book.answer_to(question)) is not None:
                return {"status": "answered", "answer": answer}
            if question not in {q.message_id for q in nestor.message_book.pending()} | {
                q.message_id for q in nestor.message_book.open_questions()
            }:
                return {"status": "not delivered", "note": "it could not reach them; go on without it or say so"}
            return {"status": "waiting"}

        @self.mcp.tool(description=DESCRIPTIONS["attach_file"])
        async def attach_file(task: str, name: str, media_type: str, content: str, ctx: Context) -> dict[str, object]:
            found = await self._task(ctx, task, "attach_file")
            try:
                data = base64.b64decode(content, validate=True)
            except ValueError:
                raise ToolError("content must be base64") from None
            if len(data) > FILE_BYTES:
                raise ToolError(f"larger than {FILE_BYTES // 1_000_000} MB")
            kind = AttachmentKind.IMAGE if media_type.startswith("image/") else AttachmentKind.FILE
            kept = await nestor.tasks.add_file(
                found, Attachment(kind=kind, data=data, media_type=media_type, name=name)
            )
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

    async def _sent(self, task: Task) -> list[Any]:
        """The files sent in the conversation the task came from, until it was handed over."""
        if task.exchange is None:
            return []
        turns = await self._nestor.journal.history(UserTurn, session=task.origin.session)
        return [
            attached
            for turn in turns
            if turn.exchange is not None
            and turn.exchange.conversation_id == task.exchange.conversation_id
            and turn.at <= task.started_at
            for attached in turn.attachments
        ]

    async def _run_memory(
        self, name: str, arguments: Mapping[str, object], context: ToolContext
    ) -> Mapping[str, object]:
        tool = next(t for t in self._nestor.memory_tools.tools() if t.name == name)
        try:
            output = await tool.run(arguments, context)
        except ToolFailed as failed:
            raise ToolError(str(failed)) from None
        if not isinstance(output, Mapping):
            raise ToolError(f"{name} answered nothing to read")
        return output


class _Guarded:
    """The MCP endpoint behind the executor's key: a request without a key that belongs to an executor, or over its
    rate, is refused before the MCP app sees it."""

    def __init__(self, app: StreamableHTTPASGIApp, caller: Callable[[str], str | None]) -> None:
        self._app, self._caller = app, caller

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        headers = dict(scope.get("headers") or ())
        bearer = headers.get(b"authorization", b"").decode("latin-1")
        key = bearer.removeprefix("Bearer ").strip() if bearer.startswith("Bearer ") else ""
        executor = self._caller(key) if key else None
        if executor is None:
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        scope[SCOPE_KEY] = executor
        await self._app(scope, receive, send)
