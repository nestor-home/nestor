"""Events of unprompted messages: every delivery, and every failure to deliver, with its reason."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address


class Delivered(Event, event_type="initiative.delivered"):
    address: Address
    about: str  # why the agent spoke up: "task 3f2a1c ended"
    person: PersonId | None = None


class DeliveryFailed(Event, event_type="initiative.undeliverable"):
    about: str
    tried: tuple[Address, ...]
    person: PersonId | None = None


class DeliveryConsidered(Event, event_type="initiative.considered"):
    """The delivery decision and its reason: what answers "why did it speak to me?"."""

    about: str
    reason: str
    spoken: Address | None = None
    written: Address | None = None
    person: PersonId | None = None
