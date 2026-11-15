"""What every tool builds on: the running task its call is for (or the one refusal), whoever asked for it, and the
conversation it was handed over in."""

from dataclasses import dataclass
from datetime import datetime

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from nestor.core import PersonId
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.conversation import Attached, NotificationTurn, UserTurn
from nestor.modules.conversation.history import in_conversation
from nestor.runtime import Nestor

SCOPE_KEY = "nestor.executor"  # the executor a request's key belongs to, set by `guard` before the MCP app sees it
REFUSED = "not a running task of yours"  # whatever is wrong: the key, the task, its executor, its end
FILE_BYTES = 20_000_000  # largest file read or handed back through the server


@dataclass(frozen=True, slots=True)
class Sent:
    """The conversation a task was handed over in, until then."""

    since: datetime  # when it started
    files: tuple[Attached, ...]  # what people sent in it


class TaskAccess:
    def __init__(self, nestor: Nestor) -> None:
        self.nestor = nestor
        self._sent: dict[str, Sent] = {}  # by running task: what was said and sent before it, read once

    async def task(self, ctx: Context, task: str, tool: str) -> Task:
        """The running task of the calling executor whose capability is `task`; the call journaled either way."""
        request = ctx.request_context.request
        assert request is not None  # served over HTTP, behind `guard`, which named the executor
        found = await self.nestor.tasks.admit(request.scope[SCOPE_KEY], task, tool)
        if found is None:
            raise ToolError(REFUSED)
        return found

    def requester(self, task: Task) -> PersonId:
        """Who asked for the task: whose memory a tool reads or keeps, and whom it asks."""
        if task.requested_by is None:
            raise ToolError("nobody asked for this task: nothing of anyone's to read, keep or ask")
        return task.requested_by

    async def sent(self, task: Task) -> Sent:
        """The conversation the task was handed over in, until then: when it started and the files sent in it."""
        if (known := self._sent.get(task.id)) is not None:
            return known
        opened: list[UserTurn | NotificationTurn] = []  # what opened its turns: a person, or Nestor (a wake-up)
        if task.exchange is not None:
            history = await self.nestor.journal.history(UserTurn, NotificationTurn, session=task.origin.session)
            opened = [t for t in in_conversation(history, task.exchange.conversation_id) if t.at <= task.started_at]
        found = Sent(
            since=opened[0].at if opened else task.started_at,
            files=tuple(a for turn in opened if isinstance(turn, UserTurn) for a in turn.attachments),
        )
        running = {t.id for t in self.nestor.tasks.running()}
        self._sent = {k: v for k, v in self._sent.items() if k in running} | {task.id: found}  # ended tasks go
        return found
