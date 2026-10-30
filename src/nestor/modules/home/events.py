"""Presence events: recorded so a delivery decision can be explained later."""

from nestor.core import Event, PersonId


class PresenceChanged(Event, event_type="presence.changed"):
    person: PersonId
    home: bool | None
    room: str | None = None
