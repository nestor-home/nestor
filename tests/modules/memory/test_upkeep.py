"""The nightly upkeep: each place tidied by the consolidation model, only what holds applied, every change journaled
with its reason, and a night missed while stopped caught up at start."""

import asyncio
import json
from datetime import UTC, datetime, time, timedelta

import pytest

from nestor.core import PersonId
from nestor.modules.cognition.model import ModelRequest
from nestor.modules.household import Household, Person
from nestor.modules.journal import Journal
from nestor.modules.memory import (
    HOME,
    Memories,
    Memory,
    MemoryCorrected,
    MemoryRetired,
    MemoryUpkept,
    Place,
    Retirement,
    Upkeep,
)
from nestor.testing.cognition import ScriptedModel
from nestor.testing.journal import MemoryEventLog
from nestor.testing.memory import InMemoryMemoryStore

LEA = Person(id=PersonId("lea"), name="Léa")
NOW = datetime(2026, 11, 26, 2, 30, tzinfo=UTC)  # 03:30 in Paris
ROOF = Place.parse("projects/toiture")


def memory(id: str, text: str, place: Place, day: str) -> Memory:
    at = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return Memory(id=id, text=text, place=place, created_at=at, updated_at=at)


def tidy(request: ModelRequest) -> str:
    """What a model answers for each place, right and wrong mixed."""
    system = request.messages[0].content
    if "people/lea (Léa)" in system:
        return json.dumps(
            {
                "merge": [{"ids": ["m4", "m3"], "text": "Léa aime le thé et en boit chaque jour."}],
                "retire": [
                    {"id": "m1", "by": "m2", "why": "elle remange du poisson"},
                    {"id": "m2", "by": "m1", "why": "an older one never overrides"},
                    {"id": "m3", "by": "m2", "why": "already merged"},
                    {"id": "zz", "by": "m2", "why": "not of this place"},
                    {"id": "m5", "until": "mars", "why": "no date"},
                ],
            }
        )
    if str(ROOF) in system:
        return json.dumps({"retire": [{"id": "r1", "until": "2026-03-03", "why": "le couvreur est passé"}]})
    return "Je ne sais pas."


async def test_each_place_is_tidied_only_as_far_as_it_holds_and_every_change_is_journaled() -> None:
    journal = Journal(MemoryEventLog())
    memories = Memories(journal, InMemoryMemoryStore())
    lea = Place.of(LEA.id)
    for kept in (
        memory("m1", "Léa est végétarienne.", lea, "2025-01-10"),
        memory("m2", "Léa remange du poisson.", lea, "2026-08-01"),
        memory("m3", "Léa aime le thé.", lea, "2025-02-01"),
        memory("m4", "Léa boit du thé.", lea, "2026-09-01"),
        memory("m5", "Léa court un semi-marathon en mars.", lea, "2026-01-05"),
        memory("r1", "Le couvreur passe le 3 mars 2026.", ROOF, "2026-02-01"),
        memory("h1", "La chaudière est révisée chaque septembre.", HOME, "2026-09-20"),
    ):
        await memories.store.put(kept)
    upkeep = Upkeep(
        journal,
        ScriptedModel(tidy, tidy, tidy),
        memories,
        Household([LEA]),
        at=time(3, 30),
        assistant="Richie",
        timezone="Europe/Paris",
        clock=lambda: NOW,
    )

    done = await upkeep.upkeep()

    left = {m.id: m.text for m in await memories.store.everything()}
    assert left == {
        "m2": "Léa remange du poisson.",
        "m4": "Léa aime le thé et en boit chaque jour.",  # kept on the latest, whatever the model listed first
        "m5": "Léa court un semi-marathon en mars.",  # no date that passed: kept
        "h1": "La chaudière est révisée chaque septembre.",
    }
    retired = {
        e.memory_id: (e.reason, e.why, e.into, e.merged_text, e.text) for e in await journal.history(MemoryRetired)
    }
    assert retired == {
        "m3": (Retirement.MERGED, None, "m4", "Léa aime le thé et en boit chaque jour.", "Léa aime le thé."),
        "m1": (Retirement.STALE, "elle remange du poisson", None, None, "Léa est végétarienne."),
        "r1": (Retirement.STALE, "le couvreur est passé", None, None, "Le couvreur passe le 3 mars 2026."),
    }
    (merged,) = await journal.history(MemoryCorrected)
    assert (merged.memory_id, merged.merged) == ("m4", ("m3",))
    assert (done.places, done.merged, done.retired, done.failed) == (3, 1, 2, ("home",)), "an unreadable answer"
    assert await journal.history(MemoryUpkept) == [done]


async def test_a_night_missed_while_stopped_is_caught_up_at_start_and_the_next_waits_for_its_hour() -> None:
    journal = Journal(MemoryEventLog())
    model = ScriptedModel()
    upkeep = Upkeep(
        journal,
        model,
        Memories(journal, InMemoryMemoryStore()),
        Household([LEA]),
        at=time(3, 30),
        assistant="Richie",
        timezone="Europe/Paris",
        clock=lambda: NOW + timedelta(hours=12),
    )
    assert upkeep.due_after(NOW + timedelta(hours=12)) == datetime(2026, 11, 27, 3, 30, tzinfo=upkeep.zone)
    await journal.publish(MemoryUpkept(source="memory", places=0, merged=0, retired=0, at=NOW - timedelta(days=2)))
    upkept = journal.subscribe(MemoryUpkept)
    async with upkeep:
        await asyncio.wait_for(upkept.next(), 1.0)
        with pytest.raises(TimeoutError):  # the next night only
            await asyncio.wait_for(upkept.next(), 0.05)
