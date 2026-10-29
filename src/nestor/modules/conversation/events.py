"""Events of the dialogue, whatever the channel (voice, messaging, web)."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address
from nestor.modules.conversation.types import FallbackReason


class UserTurn(Event, event_type="conversation.turn.user"):
    address: Address
    text: str
    person: PersonId | None = None


class AssistantTurn(Event, event_type="conversation.turn.assistant"):
    """What the user actually received: on voice, only the part played before an interruption."""

    address: Address
    text: str
    interrupted: bool = False


class FallbackSpoken(Event, event_type="conversation.fallback"):
    """A provider failed or stalled and the assistant said so instead of staying silent."""

    address: Address
    reason: FallbackReason
