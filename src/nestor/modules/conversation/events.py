"""Events of the dialogue, whatever the channel (voice, messaging, web), each with the conversation
and the turn it belongs to (`exchange`)."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange, Medium
from nestor.modules.conversation.types import About, Attached, FallbackReason, Mentioned
from nestor.modules.identity import Speaker


class UserTurn(Event, event_type="conversation.turn.user"):
    """A message to the assistant, said or typed (`medium`), and who said it as far as anyone knows (`speaker`). Its
    `exchange.turn_id` is the turn it opens.

    `text` is the person's words: what they typed, then what their voice messages said. `attachments` are the files
    that came with it, voice messages included; `mentions` what the words name with `@`."""

    address: Address
    text: str
    exchange: Exchange
    medium: Medium
    speaker: Speaker
    attachments: tuple[Attached, ...] = ()
    mentions: tuple[Mentioned, ...] = ()

    @property
    def person(self) -> PersonId | None:
        return self.speaker.person


class SpeakerDeclared(Event, event_type="speaker.declared"):
    """Someone on a shared device said who they are: it holds for the rest of the conversation, unless their voice
    says otherwise. It personalises; it never authorises."""

    address: Address
    person: PersonId
    exchange: Exchange | None = None


class NotificationTurn(Event, event_type="conversation.turn.notification"):
    """A notification Nestor brought into the conversation (a task's result, a watch, a message to pass on): it opens
    the turn its answer belongs to. Said by nobody in the conversation; `person` is whom it is for."""

    address: Address
    text: str
    about: About
    exchange: Exchange
    person: PersonId | None = None


class AssistantTurn(Event, event_type="conversation.turn.assistant"):
    """What the user actually received: on voice, only the part played before an interruption. In the turn it
    answers: a person's message, or a notification of Nestor's (an unprompted message)."""

    address: Address
    text: str
    interrupted: bool = False
    exchange: Exchange | None = None  # None outside a turn: composed, or cut before its turn began


class FallbackSpoken(Event, event_type="conversation.fallback"):
    """A provider failed or stalled and the assistant said so instead of staying silent."""

    address: Address
    reason: FallbackReason
    exchange: Exchange | None = None  # None outside a turn: composed, or cut before its turn began


class AnswerCut(Event, event_type="conversation.turn.cut"):
    """The user cut in while a fully written answer was still being spoken: only `heard` reached them."""

    answer: str  # id of the AssistantTurn
    heard: str
    exchange: Exchange | None = None  # the turn of the answer it cuts


class AnswerAttached(Event, event_type="conversation.turn.attached"):
    """Files went out with an answer, kept like the files people send: its recording when it went out as a voice
    message, what tools made for it (a picture)."""

    answer: str  # id of the AssistantTurn
    files: tuple[Attached, ...]
    exchange: Exchange | None = None


class ConversationTitled(Event, event_type="conversation.titled"):
    """A conversation got its title, written from its first exchange: what lists show for it."""

    conversation_id: str
    title: str
