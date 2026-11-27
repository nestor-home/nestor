"""Events of sensitive actions: the confirmation asked of the person, then their answer."""

from collections.abc import Mapping
from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.channels import Address


class ConfirmationRequested(Event, event_type="confirmation.requested"):
    """`person` is asked, on their own account, to confirm `tool` with `arguments`, asked for in `origin`. `turn`: the
    turn of their conversation it was asked in, when they asked there; `None` when it is asked in writing."""

    confirmation_id: str
    person: PersonId
    tool: str
    arguments: Mapping[str, object]
    origin: Address
    turn: str | None
    expires_at: datetime


class ConfirmationAnswered(Event, event_type="confirmation.answered"):
    confirmation_id: str
    approved: bool
