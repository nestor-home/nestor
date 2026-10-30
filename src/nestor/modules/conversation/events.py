"""Events of the dialogue, whatever the channel (voice, messaging, web).

v2 of each: `exchange`, the conversation and the turn the event belongs to. Records of version 1 were
written before conversations were counted: they read with `exchange` set to `None`.
"""

from nestor.core import Event, PersonId
from nestor.core.events import JSON
from nestor.modules.channels import Address, Exchange, before_exchanges
from nestor.modules.conversation.types import FallbackReason


class UserTurn(Event, event_type="conversation.turn.user", version=2):
    """A message to the assistant. Its `exchange.turn_id` is the turn it opens."""

    address: Address
    text: str
    person: PersonId | None = None
    exchange: Exchange | None = None  # None only in records of version 1

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class AssistantTurn(Event, event_type="conversation.turn.assistant", version=2):
    """What the user actually received: on voice, only the part played before an interruption. In the
    turn it answers, or in a turn of its own when it was unprompted (a delivery)."""

    address: Address
    text: str
    interrupted: bool = False
    exchange: Exchange | None = None  # None only in records of version 1

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class FallbackSpoken(Event, event_type="conversation.fallback", version=2):
    """A provider failed or stalled and the assistant said so instead of staying silent."""

    address: Address
    reason: FallbackReason
    exchange: Exchange | None = None  # None only in records of version 1

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class AnswerCut(Event, event_type="conversation.turn.cut", version=2):
    """The user cut in while a fully written answer was still being spoken: only `heard` reached them.

    v2: `answer` was named `turn`, a word that now means the whole turn (in `exchange`)."""

    answer: str  # id of the AssistantTurn
    heard: str
    exchange: Exchange | None = None  # None only in records of version 1

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        rest = {k: v for k, v in payload.items() if k != "turn"}
        return before_exchanges({**rest, "answer": payload.get("turn")})
