"""A conversation's recent history, rebuilt from the journal for the model."""

from nestor.core import Event
from nestor.modules.channels import Address
from nestor.modules.cognition.model import Message, Role, ToolCall
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, UserTurn
from nestor.modules.journal import Journal

HISTORY_EVENTS = (UserTurn, AssistantTurn, AnswerCut, ToolCalled, ToolCompleted)


async def recent_history(journal: Journal, address: Address, *, max_events: int = 60) -> tuple[Message, ...]:
    """The last exchanges of this conversation, whatever the process that held them (restarts included)."""
    events = await journal.history(*HISTORY_EVENTS, session=address.session, newest_first=True, limit=max_events)
    return to_messages(list(reversed(events)))


def to_messages(events: list[Event]) -> tuple[Message, ...]:
    """Turn log events into model messages. A tool call without its result (crash midway, or cut by
    the window) is dropped, since models refuse unanswered calls. The history may open on an
    assistant message: an unprompted delivery the user is now answering."""
    results = {e.call_id: e for e in events if isinstance(e, ToolCompleted)}
    heard = {e.turn: e.heard for e in events if isinstance(e, AnswerCut)}
    messages: list[Message] = []
    for event in events:
        if isinstance(event, UserTurn):
            messages.append(Message.user(event.text))
        elif isinstance(event, AssistantTurn) and (text := heard.get(event.id, event.text)):
            messages.append(Message(role=Role.ASSISTANT, content=text))
        elif isinstance(event, ToolCalled) and (result := results.get(event.call_id)):
            call = ToolCall(event.call_id, event.name, event.arguments)
            messages.append(Message(role=Role.ASSISTANT, tool_calls=(call,)))
            messages.append(Message(role=Role.TOOL, content=result.output, tool_call_id=event.call_id))
    return tuple(messages)
