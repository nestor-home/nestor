"""Dates as the household reads them, in the assistant's timezone."""

from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def french_time(moment: datetime, timezone: str, *, now: datetime) -> str:
    """`aujourd'hui 14:05`, `28 oct. 09:12`, `28 oct. 2025 09:12`."""
    zone = ZoneInfo(timezone)
    local, today = moment.astimezone(zone), now.astimezone(zone)
    clock = local.strftime("%H:%M")
    if local.date() == today.date():
        return f"aujourd'hui {clock}"
    day = f"{local.day} {MONTHS[local.month - 1]}"
    return f"{day} {clock}" if local.year == today.year else f"{day} {local.year} {clock}"
