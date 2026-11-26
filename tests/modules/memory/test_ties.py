"""A memory tied to a task or an alert is retired, with its reason journaled, when that one ends; a task's note
becomes a memory only when Nestor keeps it."""

import asyncio
from collections.abc import Sequence

import pytest

from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation import TaskArchived
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.household import Household, Person
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, MemoryRecorded, MemoryRetired, Retirement, Tie, Ties
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.memory.episodes import Episodes
from nestor.testing.journal import MemoryEventLog
from nestor.testing.memory import InMemoryEpisodeStore, InMemoryMemoryStore

LEA, HUGO = Person(id=PersonId("lea"), name="Léa"), Person(id=PersonId("hugo"), name="Hugo")
CHAT = Address("telegram", "7")
NOTES = {"t1": ["Annonces lues sur trois sites, filtre à 2 000 €.", "Le vendeur de Lyon répond sous 48 h."]}


def notes(task: str, person: PersonId | None) -> Sequence[str] | None:
    return NOTES.get(task) if person == LEA.id else None


def home(running: set[str]) -> tuple[Journal, Memories, Ties, dict]:
    journal = Journal(MemoryEventLog())
    memories = Memories(journal, InMemoryMemoryStore())
    ties = Ties(journal, memories, [Tie("task", TaskArchived, lambda e: e.task_id, lambda task: task in running)])
    tools = MemoryTools(
        memories,
        Episodes(journal, InMemoryEpisodeStore()),
        Household([LEA, HUGO]),
        journal,
        assistant="Richie",
        ties=ties,
        notes=notes,
    )
    return journal, memories, ties, {t.spec.name: t for t in tools.tools()}


async def test_a_memory_tied_to_a_task_is_retired_with_its_reason_when_the_task_ends() -> None:
    journal, memories, ties, tools = home(running={"t1", "t2"})
    lea = ToolContext(address=CHAT, speaker=Speaker.account(LEA.id))
    tied = await tools["remember"].run(
        {"text": "Léa veut un vélo cargo à moins de 2 000 €.", "place": "people/lea", "tied_to": " task:t1 "}, lea
    )
    other = await tools["remember"].run(
        {"text": "Hugo cherche un vélo.", "place": "people/hugo", "tied_to": "task:t2"}, lea
    )
    for wrong in ("task:t9", "alert:prix", "t1"):
        with pytest.raises(ToolFailed):
            await tools["remember"].run({"text": "x", "place": "home", "tied_to": wrong}, lea)

    retired = journal.subscribe(MemoryRetired)
    async with ties:
        await journal.publish(TaskArchived(source="tasks", task_id="t1"))
        event = await asyncio.wait_for(retired.next(), 1.0)

    assert (event.memory_id, event.reason, event.tied_to, event.text) == (
        tied["memory_id"],
        Retirement.ENDED,
        "task:t1",
        "Léa veut un vélo cargo à moins de 2 000 €.",
    )
    assert [m.id for m in await memories.store.everything()] == [other["memory_id"]], "only what that task tied"


async def test_a_note_of_a_task_becomes_a_memory_only_when_kept_and_says_where_it_came_from() -> None:
    journal, memories, _, tools = home(running=set())
    lea = ToolContext(address=CHAT, speaker=Speaker.account(LEA.id))
    assert await memories.store.everything() == [], "a task's notes are no memories"

    kept = await tools["keep_note"].run(
        {"task": "t1", "note": 2, "text": "Le vendeur de vélos de Lyon répond sous 48 h.", "place": "projects/velo"},
        lea,
    )

    (recorded,) = await journal.history(MemoryRecorded)
    assert (recorded.memory_id, recorded.task, recorded.place, recorded.told_by) == (
        kept["memory_id"],
        "t1",
        "projects/velo",
        LEA.id,
    )
    hugo = ToolContext(address=CHAT, speaker=Speaker.account(HUGO.id))
    for arguments, context in (
        ({"task": "t1", "note": 3, "text": "x", "place": "home"}, lea),
        ({"task": "t1", "note": 1, "text": "x", "place": "home"}, hugo),
    ):
        with pytest.raises(ToolFailed):
            await tools["keep_note"].run(arguments, context)
