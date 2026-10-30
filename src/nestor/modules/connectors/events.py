"""Connection events. Secrets are never part of them."""

from nestor.core import Event, PersonId
from nestor.core.events.codec import JSON, encode
from nestor.core.i18n import Message
from nestor.modules.connectors.types import Status


class ConnectionCreated(Event, event_type="connection.created"):
    connection_id: str
    kind: str
    account: str
    owner: PersonId | None = None


_REASONS = {
    "refresh refused by the provider": "connection-refresh-refused",
    "access expired and no refresh token": "connection-no-refresh-token",
}


class ConnectionChanged(Event, event_type="connection.changed", version=2):
    """v2: `reason` is a message (`connection-*`), `None` when there is none to give."""

    connection_id: str
    status: Status
    disabled_tools: tuple[str, ...] = ()
    confirm_writes: bool = True
    reason: Message | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        text = str(payload.get("reason") or "")
        message = Message(_REASONS[text]) if text in _REASONS else Message.of("connection-reason-other", detail=text)
        return {**payload, "reason": encode(message) if text else None}


class ConnectionRemoved(Event, event_type="connection.removed"):
    connection_id: str
