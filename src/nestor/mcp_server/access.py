"""What every tool builds on: the running task its call is for (or the one refusal), whoever asked for it, when the
conversation it was handed over in started, and the links to its files."""

from datetime import datetime

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from nestor.core import PersonId
from nestor.mcp_server.links import Links
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.conversation import NotificationTurn, UserTurn
from nestor.modules.conversation.history import in_conversation
from nestor.runtime import Nestor

SCOPE_KEY = "nestor.executor"  # the executor a request's key belongs to, set by `guard` before the MCP app sees it
REFUSED = "not a running task of yours"  # whatever is wrong: the key, the task, its executor, its end
FILE_BYTES = 20_000_000  # largest file read or handed back through the server


class TaskAccess:
    def __init__(self, nestor: Nestor, links: Links) -> None:
        self.nestor, self.links = nestor, links
        self._since: dict[str, datetime] = {}  # by running task: when its conversation started, read once

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

    async def since(self, task: Task) -> datetime:
        """When the conversation the task was handed over in started: its first turn, a person's or Nestor's (a
        wake-up)."""
        if (known := self._since.get(task.id)) is not None:
            return known
        found = task.started_at
        if task.exchange is not None:
            history = await self.nestor.journal.history(UserTurn, NotificationTurn, session=task.origin.session)
            found = next((t.at for t in in_conversation(history, task.exchange.conversation_id)), found)
        running = {t.id for t in self.nestor.tasks.running()}
        self._since = {k: v for k, v in self._since.items() if k in running} | {task.id: found}  # ended tasks go
        return found
