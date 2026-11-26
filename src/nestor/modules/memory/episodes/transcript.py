"""A past conversation as it was heard, rebuilt from the journal: who said what, and when, in the household's
clock, with the tools Nestor used in it, briefly (a question answered by a tool is otherwise an empty exchange).
What the consolidation reads, and what `read_conversation` gives back.

A conversation is followed by its id, whatever session its turns were written under."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.core import shorten
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted, ToolReturned
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, NotificationTurn, UserTurn
from nestor.modules.conversation.history import heard, in_conversation
from nestor.modules.household import Household
from nestor.modules.journal import Journal

ARGUMENTS = 120  # characters of a call's arguments kept
OUTPUT = 300  # characters of what it gave back


async def transcript(
    journal: Journal, household: Household, *, conversation: str, since: datetime, assistant: str, timezone: str
) -> list[str]:
    """One line per message and per tool call, in the order they happened; an answer cut short keeps only what was
    heard of it."""
    events = await journal.history(
        UserTurn, NotificationTurn, AssistantTurn, AnswerCut, ToolCalled, ToolCompleted, ToolReturned, since=since
    )
    ours = sorted(in_conversation(events, conversation), key=lambda e: e.at)  # as it happened, whenever written
    cut = heard(ours)
    called = {e.call_id: e for e in ours if isinstance(e, ToolCalled)}
    zone = ZoneInfo(timezone)
    lines = []
    for event in ours:
        if isinstance(event, UserTurn):
            said, who = event.text, household.name_of(event.person, "Someone")
        elif isinstance(event, NotificationTurn):  # what Nestor brought in (a task's result): its answer needs it
            said, who = event.text, f"(for {assistant}, {event.about})"
        elif isinstance(event, AssistantTurn):
            said, who = cut.get(event.id, event.text), assistant
        elif isinstance(event, ToolCompleted | ToolReturned):
            call = called.get(event.call_id)
            arguments = shorten(json.dumps(call.arguments, ensure_ascii=False), ARGUMENTS) if call else ""
            outcome = shorten(event.output, OUTPUT) if event.ok else f"failed: {shorten(event.output, OUTPUT)}"
            said, who = f"[{event.name} {arguments}] {outcome}", f"({assistant}'s tool)"
        else:
            continue
        if said:
            lines.append(f"[{event.at.astimezone(zone):%H:%M}] {who}: {said}")
    return lines
