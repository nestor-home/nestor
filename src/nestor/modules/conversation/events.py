"""Events of the dialogue, whatever the channel (voice, messaging, web), each with the conversation
and the turn it belongs to (`exchange`)."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.conversation.types import FallbackReason


class UserTurn(Event, event_type="conversation.turn.user"):
    """A message to the assistant. Its `exchange.turn_id` is the turn it opens."""

    address: Address
    text: str
    exchange: Exchange
    person: PersonId | None = None


class AssistantTurn(Event, event_type="conversation.turn.assistant"):
    """What the user actually received: on voice, only the part played before an interruption. In the
    turn it answers, or in a turn of its own when it was unprompted (a delivery)."""

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
