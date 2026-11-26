"""What every tool builds on: the running task its call is for (or the one refusal), whoever asked for it, when the
conversation it was handed over in started, and the links to its files."""

from datetime import datetime

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from nestor.core import PersonId
from nestor.mcp_server.links import Links
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.conversation import About, NotificationTurn, Source, UserTurn
from nestor.modules.conversation.history import in_conversation
from nestor.modules.usage import CallPurpose, attribute
from nestor.runtime import Nestor

SCOPE_KEY = "nestor.executor"  # the executor a request's key belongs to, set by `guard` before the MCP app sees it
REFUSED = "not a working turn of yours"  # whatever is wrong: the key, the task, its executor, the turn's end
FILE_BYTES = 20_000_000  # largest file read or handed back through the server


class TaskAccess:
    def __init__(self, nestor: Nestor, links: Links) -> None:
        self.nestor, self.links = nestor, links
        self._since: dict[str, datetime] = {}  # by running task: when its conversation started, read once

    async def task(self, ctx: Context, task: str, tool: str) -> Task:
        """The task of the calling executor whose working turn's capability is `task`; the call journaled either way.
        What the tool then asks of the models is the task's, on behalf of its owner."""
        request = ctx.request_context.request
        assert request is not None  # served over HTTP, behind `guard`, which named the executor
        found = await self.nestor.tasks.admit(request.scope[SCOPE_KEY], task, tool)
        if found is None:
            raise ToolError(REFUSED)
        origin = found.turn.origin
        attribute(  # the tool's own call: every tool starts here
            purpose=CallPurpose.TASK,
            person=found.owner,
            channel=origin.channel,
            session=origin.session,
            origin=About(Source.TASK, found.id).key,
        )
        return found

    def owner(self, task: Task) -> PersonId:
        """Whose task it is: whose memory a tool reads."""
        if task.owner is None:
            raise ToolError("this task is nobody's: nothing of anyone's to read")
        return task.owner

    async def since(self, task: Task) -> datetime:
        """When the conversation its working turn was given in started (in that turn's own channel conversation, not
        necessarily the task's first): its first turn, a person's or Nestor's (a wake-up)."""
        turn = task.turn
        if (known := self._since.get(turn.id)) is not None:
            return known
        found = turn.started_at
        if turn.exchange is not None:
            history = await self.nestor.journal.history(UserTurn, NotificationTurn, session=turn.origin.session)
            found = next((t.at for t in in_conversation(history, turn.exchange.conversation_id)), found)
        working = {t.turn.id for t in self.nestor.tasks.working()}
        self._since = {k: v for k, v in self._since.items() if k in working} | {turn.id: found}  # ended turns go
        return found
