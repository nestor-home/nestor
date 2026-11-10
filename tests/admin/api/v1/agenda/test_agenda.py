"""What the agent will do on its own, as the admin shows it: wake-ups, messages and questions on their way, and
sensitive actions waiting for their person — each visible to whom it concerns."""

from datetime import time, timedelta
from pathlib import Path

from nestor.core import PersonId, utc_now
from nestor.modules.accounts import Role
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolCall
from nestor.modules.cognition.tools import ToolContext
from nestor.modules.identity import Identified, Speaker
from nestor.modules.initiative import Day

from ....harness import Harness

TELEGRAM = Address("telegram", "42")
SALON = Address("speaker", "salon")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


async def test_wake_ups_come_soonest_first_each_to_whom_it_was_set_for_and_cancel(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        book = admin.nestor.schedule_book
        later = await book.create("Arrose les plantes", owner=MATHILDE, times=(time(8),), days=(Day.SAT, Day.SUN))
        soon = await book.create(
            "Rappelle le pain", owner=MATHIS, created_in=TELEGRAM, at=utc_now() + timedelta(hours=1)
        )
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        owner, member = await admin.api(), await admin.api("mathilde")

        listed = (await owner.get("/api/v1/schedules")).json()
        assert [s["id"] for s in listed["schedules"]] == [soon.id, later.id]
        assert listed["timezone"] == "Europe/Paris"
        weekly = listed["schedules"][1]
        assert (weekly["recurring"], weekly["times"], weekly["days"], weekly["owner"]["id"]) == (
            True,
            ["08:00"],
            ["sat", "sun"],
            "mathilde",
        )
        assert listed["schedules"][0]["origin"] == {"session": "telegram:42", "channel": "telegram"}

        mine = (await member.get("/api/v1/schedules")).json()["schedules"]
        assert [s["id"] for s in mine] == [later.id], "a member sees the wake-ups set for them"
        refused = await member.post(f"/api/v1/schedules/{soon.id}/cancel")
        assert refused.json()["error"]["code"] == "schedule_unknown"
        assert (await member.post(f"/api/v1/schedules/{later.id}/cancel")).status_code == 204
        assert set(book.schedules) == {soon.id}


async def test_open_questions_show_to_whom_they_concern(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        book = admin.nestor.message_book
        await admin.nestor.messenger.close()  # the test delivers it: Mathilde has no channel here
        question = await book.request(MATHILDE, "Tu rentres à quelle heure ?", requested_by=MATHIS, expects_reply=True)
        await book.delivered(question.message_id, TELEGRAM)
        for login in ("mathilde", "lucie"):
            await admin.account(login, Role.MEMBER, login)
        seen = {
            login: [m["id"] for m in (await (await admin.api(login)).get("/api/v1/messages")).json()["questions"]]
            for login in ("mathis", "mathilde", "lucie")
        }
        asked = (await (await admin.api()).get("/api/v1/messages")).json()["questions"][0]

    assert seen == {"mathis": [question.message_id], "mathilde": [question.message_id], "lucie": []}
    assert (asked["to"]["id"], asked["requested_by"]["id"], asked["expects_reply"]) == ("mathilde", "mathis", True)


async def test_a_sensitive_action_waits_for_its_person_who_alone_answers_it_here(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        confirmations = admin.nestor.confirmations
        await confirmations.confirm(
            ToolCall("c1", "unlock", {"door": "entrée"}),
            ToolContext(address=SALON, speaker=Speaker(MATHIS, Identified.SAID)),
            about="Unlocks a door.",
        )
        await admin.account("mathilde", Role.ADMIN, "mathilde")
        owner, other = await admin.api(), await admin.api("mathilde")
        (waiting,) = (await owner.get("/api/v1/confirmations")).json()
        assert (waiting["person"]["id"], waiting["tool"], waiting["arguments"], waiting["yours"]) == (
            "mathis",
            "unlock",
            {"door": "entrée"},
            True,
        )
        assert (await other.get("/api/v1/confirmations")).json()[0]["yours"] is False, "an admin sees it, not theirs"
        path = f"/api/v1/confirmations/{waiting['id']}/answer"
        assert (await other.post(path, {"approved": True})).json()["error"]["code"] == "confirmation_unknown"
        assert admin.unlocked == []

        answered = (await owner.post(path, {"approved": True})).json()
        assert answered == {"approved": True, "result": "unlocked"}
        assert admin.unlocked == [{"door": "entrée"}]
        assert (await owner.get("/api/v1/confirmations")).json() == []
        assert (await owner.post(path, {"approved": True})).json()["error"]["code"] == "confirmation_unknown"
