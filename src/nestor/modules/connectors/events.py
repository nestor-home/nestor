"""Connection events. Secrets are never part of them."""

from nestor.core import Event, PersonId
from nestor.modules.connectors.types import Status


class ConnectionCreated(Event, event_type="connection.created"):
    connection_id: str
    kind: str
    account: str
    owner: PersonId | None = None


class ConnectionChanged(Event, event_type="connection.changed"):
    connection_id: str
    status: Status
    disabled_tools: tuple[str, ...] = ()
    confirm_writes: bool = True
    reason: str = ""


class ConnectionRemoved(Event, event_type="connection.removed"):
    connection_id: str
