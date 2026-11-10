"""Events of unprompted messages: every decision with its reason, and how each ended: delivered, withheld (nothing to
tell) or failed."""

from nestor.core import Event, PersonId
from nestor.core.i18n import Message
from nestor.modules.channels import Address
from nestor.modules.conversation import About


class Delivered(Event, event_type="initiative.delivered"):
    address: Address
    about: About  # why the agent spoke up: `task 3f2a1c completed`
    person: PersonId | None = None
    follow_up: bool = False  # written after what was said aloud got no reaction


class DeliveryWithheld(Event, event_type="initiative.withheld"):
    """The agent did what the notification asked and had nothing to tell (a check that found nothing): nothing was
    sent, and the notification was allowed to end so."""

    address: Address  # where it would have gone
    about: About
    person: PersonId | None = None


class DeliveryFailed(Event, event_type="initiative.undeliverable"):
    """Nowhere took it: no channel could, the model could not write it, or it wrote nothing where it had to."""

    about: About
    tried: tuple[Address, ...]
    person: PersonId | None = None


class DeliveryConsidered(Event, event_type="initiative.considered"):
    """The delivery decision and its reason: what answers "why did it speak to me?"."""

    about: About
    reason: Message
    spoken: Address | None = None
    written: Address | None = None
    person: PersonId | None = None
