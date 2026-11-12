"""Small, dependency-free helpers shared by the whole framework."""

from nestor.core.shared.clock import utc_now
from nestor.core.shared.ids import PersonId, SessionId, new_id
from nestor.core.shared.text import shorten

__all__ = ["PersonId", "SessionId", "new_id", "shorten", "utc_now"]
