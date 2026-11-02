"""A past conversation as it was heard, rebuilt from the journal: who said what, and when, in the household's
clock. What the consolidation reads, and what `read_conversation` gives back."""

from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.modules.channels import Address
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, UserTurn
from nestor.modules.conversation.history import heard, in_conversation
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
    ours = in_conversation(events, conversation)
    cut = heard(ours)
    zone = ZoneInfo(timezone)
    lines = []
    for event in ours:
        if isinstance(event, UserTurn):
            said, who = event.text, household.name_of(event.person, "Someone")
        elif isinstance(event, AssistantTurn):
            said, who = cut.get(event.id, event.text), assistant
        else:
            continue
        if said:
            lines.append(f"[{event.at.astimezone(zone):%H:%M}] {who}: {said}")
    return lines
