"""What the SQLite stores share: time as sortable text, and full-text queries that never become FTS syntax."""

import re
from datetime import UTC, datetime

_WORD = re.compile(r"\w{2,}")


def time_key(at: datetime) -> str:
    """Fixed-width UTC text, so that SQL comparisons on it follow time."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def from_time_key(key: str) -> datetime:
    return datetime.strptime(key, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def match(query: str) -> str | None:
    """Any of the words of `query`, each as a prefix (`portail*`), quoted; None when it has no word."""
    terms = _WORD.findall(query)
    return " OR ".join(f'"{t}"*' for t in terms) if terms else None
