"""Events of unprompted messages: every decision with its reason, every delivery and failure."""

import re

from nestor.core import Event, PersonId
from nestor.core.events.codec import JSON, encode
from nestor.core.i18n import Message
from nestor.modules.channels import Address


class Delivered(Event, event_type="initiative.delivered"):
    address: Address
    about: str  # why the agent spoke up: "task 3f2a1c ended"
    person: PersonId | None = None


class DeliveryFailed(Event, event_type="initiative.undeliverable"):
    about: str
    tried: tuple[Address, ...]
    person: PersonId | None = None


_PLAIN_REASONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(f"^{pattern}$"), id)
    for pattern, id in (
        (r"asked for it in writing", "delivery-asked-in-writing"),
        (r"quiet hours: nothing spoken", "delivery-quiet-hours"),
        (r"no presence information: back to the conversation it came from", "delivery-no-presence"),
        (r"(?P<person>.+) is away", "delivery-away"),
        (r"(?P<person>.+) is in a room without a satellite", "delivery-room-without-satellite"),
        (r"(?P<person>.+) is in the (?P<room>.+)", "delivery-in-room"),
        (r"no satellite where (?P<person>.+) may be", "delivery-no-satellite"),
    )
)


class DeliveryConsidered(Event, event_type="initiative.considered", version=2):
    """The delivery decision and its reason: what answers "why did it speak to me?".

    v2: `reason` is a message; v1 wrote it as an English sentence, recognised when read back."""

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        text = str(payload.get("reason", ""))
        found = ((id, match) for pattern, id in _PLAIN_REASONS if (match := pattern.match(text)))  # first wins
        id, match = next(found, ("delivery-other", None))
        message = Message(id, match.groupdict()) if match else Message.of(id, reason=text)
        return {**payload, "reason": encode(message)}

    about: str
    reason: Message
    spoken: Address | None = None
    written: Address | None = None
    person: PersonId | None = None
