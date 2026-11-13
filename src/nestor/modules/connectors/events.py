"""Connection events. Secrets are never part of them."""

from nestor.core import Event, PersonId
from nestor.core.i18n import Message
from nestor.modules.connectors.types import AuthKind, Status


class ConnectionCreated(Event, event_type="connection.created"):
    connection_id: str
    kind: str
    account: str
    auth: AuthKind
    owner: PersonId | None = None


class ConnectionChanged(Event, event_type="connection.changed"):
    """`reason` is a message (`connection-*`), `None` when there is none to give."""

    connection_id: str
    status: Status
    disabled_tools: tuple[str, ...] = ()
    confirm_writes: bool = True
    reason: Message | None = None


class ConnectionRemoved(Event, event_type="connection.removed"):
    connection_id: str
