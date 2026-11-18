"""Questions to the requester, through the message book: asked at once (`ask_requester`), their answer read later
(`check_answer`). The agent passes the answer back with `pass_answer` when the requester gives it."""

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.mcp_server.access import TaskAccess
from nestor.modules.initiative import QuestionState


def register(mcp: MCPServer, access: TaskAccess) -> None:
    book = access.nestor.message_book

    @mcp.tool(
        description=(
            "Ask the requester a question; it returns at once with the question's id: call check_answer later for"
            " their answer."
        )
    )
    async def ask_requester(task: str, question: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "ask_requester")
        requester = access.requester(found)
        asked = await book.request(
            requester,
            f'{found.executor}, working on "{found.title}": {question}',
            requested_by=requester,  # the task acts for whoever handed it over
            origin=found.origin,
            expects_reply=True,
            exchange=found.exchange,
            task=found.id,
        )
        return {"question": asked.message_id, "status": "asked"}

    @mcp.tool(description="The requester's answer to a question asked with ask_requester, once they gave it.")
    async def check_answer(task: str, question: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "check_answer")
        asked = book.get(question)
        if asked is None or asked.task != found.id:
            raise ToolError(f"no question {question} from this task")
        state = book.state(question)
        if state is QuestionState.ANSWERED:
            return {"status": "answered", "answer": book.answer_to(question)}
        if state is QuestionState.UNDELIVERED:
            return {"status": "not delivered", "note": "it could not reach them; go on without it or say so"}
        return {"status": "waiting"}
