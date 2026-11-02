"""A past conversation as it was heard, rebuilt from the journal: who said what, and when, in the household's
clock. What the consolidation reads, and what `read_conversation` gives back."""

from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.modules.channels import Address
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, UserTurn
from nestor.modules.household import Household
from nestor.modules.journal import Journal


async def transcript(
    journal: Journal,
    household: Household,
    *,
    address: Address,
    conversation: str,
    since: datetime,
    assistant: str,
    timezone: str,
) -> list[str]:
    """One line per message; an answer cut short keeps only what was heard of it."""
    events = await journal.history(UserTurn, AssistantTurn, AnswerCut, session=address.session, since=since)
    ours = [e for e in events if e.exchange is not None and e.exchange.conversation_id == conversation]
    heard = {e.answer: e.heard for e in ours if isinstance(e, AnswerCut)}
    names = {p.id: p.name for p in household.people}
    zone = ZoneInfo(timezone)
    lines = []
    for event in ours:
        if isinstance(event, UserTurn):
            who = names.get(event.person, "Someone") if event.person else "Someone"
            lines.append(f"[{event.at.astimezone(zone):%H:%M}] {who}: {event.text}")
        elif isinstance(event, AssistantTurn):
            lines.append(f"[{event.at.astimezone(zone):%H:%M}] {assistant}: {heard.get(event.id, event.text)}")
    return lines
