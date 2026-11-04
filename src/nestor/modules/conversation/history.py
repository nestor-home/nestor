"""A conversation's recent history, rebuilt from the journal for the model."""

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from nestor.core import Event
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.model import Message, Role, ToolCall
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, UserTurn
from nestor.modules.identity import Identified, Speaker
from nestor.modules.journal import Journal

HISTORY_EVENTS = (UserTurn, AssistantTurn, AnswerCut, ToolCalled, ToolCompleted)


type Names = Callable[[Speaker], str | None]


async def recent_history(
    journal: Journal, address: Address, conversation: str | None, *, max_events: int = 60, names: Names | None = None
) -> tuple[Message, ...]:
    """The last turns of this conversation, whatever the process that held them (restarts included);
    nothing without one. Earlier conversations of the session are not replayed, as in Assist."""
    if conversation is None:
        return ()
    events = await journal.history(*HISTORY_EVENTS, session=address.session, newest_first=True, limit=max_events)
    return to_messages(in_conversation(reversed(events), conversation), names=names)


class InExchange(Protocol):
    @property
    def exchange(self) -> Exchange | None: ...


def in_conversation[E: InExchange](events: Iterable[E], conversation: str) -> list[E]:
    """The events of one conversation, in the order given."""
    return [e for e in events if e.exchange is not None and e.exchange.conversation_id == conversation]


def heard(events: Iterable[Event]) -> dict[str, str]:
    """What was heard of each answer cut short, by the answer's id: all that reached the person."""
    return {e.answer: e.heard for e in events if isinstance(e, AnswerCut)}


def to_messages(events: Sequence[Event], *, names: Names | None = None) -> tuple[Message, ...]:
    """Turn log events into model messages. A tool call without its result (crash midway, or cut by
    the window) is dropped, since models refuse unanswered calls. A message written just before a
    tool call goes back with it, as the model wrote them. The history may open on an assistant
    message: an unprompted delivery the user is now answering. On a shared device, where several people may
    speak in one conversation, `names` labels each message with who said it, when anyone knows."""
    results = {e.call_id: e for e in events if isinstance(e, ToolCompleted)}
    cut = heard(events)
    messages: list[Message] = []
    for event in events:
        if isinstance(event, UserTurn):
            name = names(event.speaker) if names and event.speaker.by is not Identified.ACCOUNT else None
            messages.append(Message.user(f"[{name}] {event.text}" if name else event.text))
        elif isinstance(event, AssistantTurn) and (text := cut.get(event.id, event.text)):
            messages.append(Message(role=Role.ASSISTANT, content=text))
        elif isinstance(event, ToolCalled) and (result := results.get(event.call_id)):
            call = ToolCall(event.call_id, event.name, event.arguments)
            before = messages[-1] if messages else None
            if before is not None and before.role is Role.ASSISTANT and not before.tool_calls:
                messages[-1] = Message(role=Role.ASSISTANT, content=before.content, tool_calls=(call,))
            else:
                messages.append(Message(role=Role.ASSISTANT, tool_calls=(call,)))
            messages.append(Message(role=Role.TOOL, content=result.output, tool_call_id=event.call_id))
    return tuple(messages)
