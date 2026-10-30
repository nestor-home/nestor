"""The agent as the household sees it: what it is doing now, live on the journal's stream, its quiet
hours and the follow-ups it has scheduled, readable without the configuration's rights."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nestor.core import PersonId, utc_now
from nestor.modules.accounts import Role
from nestor.modules.memory import MemoryRecorded
from nestor.modules.satellites import SpeechActivityObserved

from ...harness import EventStream, Harness


def around_now(hours: int) -> str:
    """Quiet hours from `hours` before now to `hours` after, in the harness's time zone."""
    local = utc_now().astimezone(ZoneInfo("Europe/Paris"))
    return "-".join((local + timedelta(hours=h)).strftime("%H:%M") for h in (-hours, hours))


def heard(active: bool) -> SpeechActivityObserved:
    return SpeechActivityObserved(source="satellite", device_id="reachy-1", room="salon", active=active)


async def test_a_member_reads_what_the_agent_is_doing(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        member = await admin.api("mathilde")
        activity = await member.get("/api/v1/agent/activity")
        assert activity.status_code == 200, activity.text
        body = activity.json()
        assert {k: v for k, v in body.items() if k != "since"} == {
            "state": "idle",
            "replies": 0,
            "tasks": 0,
            "listening_rooms": [],
            "quiet": False,
        }
        await admin.nestor.journal.publish(heard(True))
        await asyncio.sleep(0.01)
        listening = (await member.get("/api/v1/agent/activity")).json()
        assert listening["state"] == "listening" and listening["listening_rooms"] == ["salon"]


async def test_the_journal_stream_says_what_the_agent_does_as_it_changes(tmp_path: Path) -> None:
    async with Harness(tmp_path, quiet_hours=around_now(1)) as admin, EventStream(await admin.api()) as stream:
        first = await stream.activity()
        assert first["state"] == "sleeping" and first["quiet"]
        await admin.nestor.journal.publish(heard(True))
        assert (await stream.activity())["state"] == "listening"
        await admin.nestor.journal.publish(heard(False))
        back = await stream.activity()
        assert back["state"] == "sleeping"
        _, item = await stream.event()
        assert item["type"] == "observation.speech.activity", "entries still come, with their position"


async def test_an_account_without_the_agents_scope_gets_entries_but_no_activity(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("lucie", Role.GUEST, "lucie")
        guest = await admin.api("lucie")
        assert (await guest.get("/api/v1/agent/activity")).status_code == 403
        async with EventStream(guest) as stream:
            assert await stream.frame() == "retry: 3000"
            await admin.nestor.journal.publish(heard(True))
            await admin.nestor.journal.publish(
                MemoryRecorded(source="memory", memory_id="m1", text="Lucie aime le thé", about=PersonId("lucie"))
            )
            frame = dict(line.split(": ", 1) for line in (await stream.frame()).splitlines())
            assert frame["event"] == "item" and json.loads(frame["data"])["detail"] == "Lucie aime le thé"


async def test_the_quiet_hours_and_scheduled_follow_ups_are_readable_each_to_whom_they_concern(
    tmp_path: Path,
) -> None:
    start, end = around_now(-2).split("-")  # from in two hours to two hours ago: not now, so it may speak
    async with Harness(tmp_path, quiet_hours=f"{start}-{end}", speaker=True) as admin:
        mathis = admin.nestor.household.person(PersonId("mathis"))
        before = utc_now()
        spoken = await admin.nestor.courier.deliver(mathis, "Le colis est arrivé.", about="watch w1")
        assert spoken is not None and str(spoken) == "voice:salon"
        initiative = (await (await admin.api()).get("/api/v1/agent/initiative")).json()
        assert initiative["quiet_hours"] == {"start": start, "end": end, "timezone": "Europe/Paris", "active": False}
        (follow_up,) = initiative["upcoming"]
        assert {k: v for k, v in follow_up.items() if k != "due_at"} == {
            "about": "watch w1",
            "delivery": "watch:w1",
            "person": {"id": "mathis", "name": "Mathis"},
            "spoken_on": "voice:salon",
            "written_on": "memory:main",
        }
        due = admin.nestor.courier.scheduled()[0].due_at
        assert due - before >= timedelta(seconds=180) and follow_up["due_at"].startswith(due.strftime("%Y-%m-%dT%H:%M"))

        await admin.account("mathilde", Role.MEMBER, "mathilde")
        mathilde = await admin.api("mathilde")
        theirs = (await mathilde.get("/api/v1/agent/initiative")).json()
        assert theirs["quiet_hours"]["start"] == start and theirs["upcoming"] == [], "only what concerns them"


async def test_without_quiet_hours_the_agent_may_speak_at_any_hour(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        assert (await (await admin.api()).get("/api/v1/agent/initiative")).json() == {
            "quiet_hours": None,
            "upcoming": [],
        }
