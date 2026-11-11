"""How the journal's turns read as the model's messages: pure functions, used by `Conversations.history`."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Protocol

from nestor.core import Event
from nestor.modules.channels import AttachmentKind, Exchange
from nestor.modules.cognition.model import Image, Message, Role, ToolCall
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted, ToolDeferred
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, NotificationTurn, UserTurn
from nestor.modules.conversation.types import Attached, Notification
from nestor.modules.identity import Identified, Speaker

HISTORY_EVENTS = (UserTurn, NotificationTurn, AssistantTurn, AnswerCut, ToolCalled, ToolCompleted, ToolDeferred)


type Names = Callable[[Speaker], str | None]


class InExchange(Protocol):
    @property
    def exchange(self) -> Exchange | None: ...


def in_conversation[E: InExchange](events: Iterable[E], conversation: str) -> list[E]:
    """The events of one conversation, in the order given."""
    return [e for e in events if e.exchange is not None and e.exchange.conversation_id == conversation]


def heard(events: Iterable[Event]) -> dict[str, str]:
    """What was heard of each answer cut short, by the answer's id: all that reached the person."""
    return {e.answer: e.heard for e in events if isinstance(e, AnswerCut)}


def notification_message(notification: Notification) -> Message:
    """A notification as the model reads it, when it answers it and every time the history is replayed: a user-role
    message that says it comes from Nestor, not from anyone in the conversation (models take such messages for the
    person's otherwise)."""
    return Message.user(f"[From Nestor itself, not said by anyone here: {notification.about}]\n{notification.text}")


def user_message(turn: UserTurn, *, name: str | None = None, images: Mapping[str, Image] | None = None) -> Message:
    """A person's message as the model reads it: their words, labelled with `name` on a shared device, and a note for
    each file that came with it. `images` are the pictures the model looks at, by digest; `None` for a model that
    does not see images. What it cannot see or hear is said, so that it tells the person rather than ignore it."""
    seen = tuple(images[a.blob.digest] for a in turn.attachments if images and a.blob.digest in images)
    notes = [_note(a, images) for a in turn.attachments]
    words = f"[{name}] {turn.text}" if name and turn.text else turn.text
    return Message.user("\n".join(part for part in (*notes, words) if part), images=seen)


def _note(attached: Attached, images: Mapping[str, Image] | None) -> str:
    named = f" ({attached.name})" if attached.name else ""
    if attached.kind is AttachmentKind.IMAGE:
        if images is None:
            return f"[An image{named} you cannot see: you do not see images]"
        if attached.blob.digest in images:
            return f"[An image{named}, attached]"
        return f"[An image{named} sent earlier, no longer shown to you]"
    match attached.kind:
        case AttachmentKind.VOICE if attached.transcript:
            return "[Said in a voice message:]"
        case AttachmentKind.VOICE if attached.transcript == "":
            return "[A voice message in which nothing could be heard]"
        case AttachmentKind.VOICE:
            return "[A voice message you could not listen to: it could not be transcribed]"
        case AttachmentKind.AUDIO if attached.transcript:
            return f"[An audio file{named}, in which is said: {attached.transcript}]"
        case AttachmentKind.AUDIO:
            return f"[An audio file{named} you cannot listen to]"
        case _:
            return f"[A file{named}, {attached.blob.media_type}, that you cannot open]"


def to_messages(
    events: Sequence[Event], *, names: Names | None = None, images: Mapping[str, Image] | None = None
) -> tuple[Message, ...]:
    """Turn log events into model messages. A tool call without its result (crash midway, or cut by
    the window) is dropped, since models refuse unanswered calls. A message written just before a
    tool call goes back with it, as the model wrote them. An unprompted message comes after the notification that
    caused it, so an answer to it knows what it was about. A call that went on in the background keeps what the model
    received then; its result comes back later as a notification. On a shared device, where several people may
    speak in one conversation, `names` labels each message with who said it, when anyone knows. `images` are the
    pictures the model looks at (`user_message`)."""
    results = {e.call_id: e for e in events if isinstance(e, ToolCompleted | ToolDeferred)}
    cut = heard(events)
    messages: list[Message] = []
    for event in events:
        if isinstance(event, UserTurn):
            name = names(event.speaker) if names and event.speaker.by is not Identified.ACCOUNT else None
            messages.append(user_message(event, name=name, images=images))
        elif isinstance(event, NotificationTurn):
            messages.append(notification_message(Notification(event.text, event.about)))
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
