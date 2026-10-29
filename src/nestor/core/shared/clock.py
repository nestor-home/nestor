"""Time helpers: every timestamp in Nestor is timezone-aware UTC."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
