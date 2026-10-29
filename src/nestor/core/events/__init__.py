"""Versioned domain events and their JSON form for the event log."""

from nestor.core.events.codec import JSON
from nestor.core.events.event import Event, Record

__all__ = ["JSON", "Event", "Record"]
