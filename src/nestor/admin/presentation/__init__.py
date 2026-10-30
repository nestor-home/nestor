"""How the admin says things: journal entries as messages, and names rendered in a reader's locale.
No sentence lives here: they are in `nestor/locales/*/*.ftl`."""

from nestor.admin.presentation.events import (
    CATEGORIES,
    OTHER_KEY,
    Category,
    EventDescriber,
    Line,
    Tone,
    subject,
    unknown_message,
)
from nestor.admin.presentation.phrasebook import Phrasebook, capability_message

__all__ = [
    "CATEGORIES",
    "OTHER_KEY",
    "Category",
    "EventDescriber",
    "Line",
    "Phrasebook",
    "Tone",
    "capability_message",
    "subject",
    "unknown_message",
]
