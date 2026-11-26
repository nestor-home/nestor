"""Alerts as the admin shows them: time ones soonest first, then those that wait for items, each with why it rang, to
whom it was set for; cancelling one ends it with who did."""

from datetime import time, timedelta
from pathlib import Path

from nestor.core import Day, PersonId, utc_now
from nestor.modules.accounts import Role
from nestor.modules.channels import Address
from nestor.modules.initiative import Alert, AlertEnd, AlertEnded, Frequency, Incoming, RingCause

from ....harness import Harness

TELEGRAM = Address("telegram", "42")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


async def test_alerts_come_soonest_first_with_why_they_rang_each_to_whom_it_was_set_for(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        book = admin.nestor.alert_book
        parcel = await book.create(
            Alert(title="Colis", instruction="Préviens Mathilde", condition="le colis", kinds=("mail",), owner=MATHILDE)
        )
        weekly = await book.create(
            Alert(
                title="Plantes du week-end",
                instruction="Arrose les plantes",
                times=(time(8),),
                days=(Day.SAT, Day.SUN),
                frequency=Frequency.EVERY_TIME,
                owner=MATHILDE,
            )
        )
        soon = await book.create(
            Alert(
                title="Pain",
                instruction="Rappelle le pain",
                at=utc_now() + timedelta(hours=1),
                owner=MATHIS,
                created_in=TELEGRAM,
                urgent=True,
            )
        )
        mail = Incoming(source="imap-1", kind="mail", title="Votre colis est livré")
        await book.ring(parcel, RingCause.MATCH, item=mail, summary="Le colis est arrivé")
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        owner, member = await admin.api(), await admin.api("mathilde")

        listed = (await owner.get("/api/v1/alerts")).json()
        assert [a["id"] for a in listed["alerts"]] == [soon.id, weekly.id, parcel.id]
        assert listed["kinds"] == ["mail"]
        first, second, third = listed["alerts"]
        assert (first["trigger"], first["urgent"], first["frequency"]) == ("at", True, "once")
        assert first["origin"] == {"session": "telegram:42", "channel": "telegram"}
        assert (second["trigger"], second["times"], second["days"], second["owner"]["id"]) == (
            "times",
            ["08:00"],
            ["sat", "sun"],
            "mathilde",
        )
        assert (third["trigger"], third["kinds"], third["rang"]) == ("events", ["mail"], 1)
        (rang,) = third["rings"]
        assert (rang["cause"], rang["item_title"], rang["summary"]) == (
            "match",
            "Votre colis est livré",
            "Le colis est arrivé",
        )

        mine = (await member.get("/api/v1/alerts")).json()["alerts"]
        assert [a["id"] for a in mine] == [weekly.id, parcel.id], "a member sees the alerts set for them"
        refused = await member.post(f"/api/v1/alerts/{soon.id}/cancel")
        assert refused.json()["error"]["code"] == "alert_unknown"
        assert (await member.post(f"/api/v1/alerts/{weekly.id}/cancel")).status_code == 204
        assert set(book.alerts) == {soon.id, parcel.id}
        (ended,) = await admin.nestor.journal.history(AlertEnded)
        assert (ended.alert_id, ended.reason, ended.by) == (weekly.id, AlertEnd.CANCELLED, MATHILDE)
