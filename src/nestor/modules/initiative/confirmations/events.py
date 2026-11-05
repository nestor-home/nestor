"""Events of sensitive actions asked aloud on a shared device: the confirmation asked in writing, then the answer."""

from collections.abc import Mapping
from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.channels import Address


class ConfirmationRequested(Event, event_type="confirmation.requested"):
    """`person` is asked, on their own account, to confirm `tool` with `arguments`, asked for in `origin`."""

    confirmation_id: str
    person: PersonId
    tool: str
    arguments: Mapping[str, object]
    origin: Address
    expires_at: datetime


class ConfirmationAnswered(Event, event_type="confirmation.answered"):
    confirmation_id: str
    approved: bool
