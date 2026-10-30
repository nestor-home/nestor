"""How the admin says things: journal events, delivery reasons and dates in French."""

from nestor.admin.presentation.dates import french_time
from nestor.admin.presentation.events import CATEGORIES, Category, EventDescriber, Line, Tone
from nestor.admin.presentation.reasons import french_reason, french_subject, french_task_status, french_watch_end

__all__ = [
    "CATEGORIES",
    "Category",
    "EventDescriber",
    "Line",
    "Tone",
    "french_reason",
    "french_subject",
    "french_task_status",
    "french_time",
    "french_watch_end",
]
