"""Tasks, watches, memories and the household through the API — each member reaching only their own."""

import asyncio
from pathlib import Path

from nestor.core import PersonId
from nestor.modules.accounts import Role
from nestor.modules.channels import Address
from nestor.modules.cognition import TaskStatus
from nestor.modules.initiative import Watch

from ...harness import Harness

TELEGRAM = Address("telegram", "42")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


async def test_a_member_sees_and_stops_their_own_tasks_only(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        hers = await admin.nestor.tasks.delegate("Trouver un plombier", origin=TELEGRAM, requested_by=MATHILDE)
        his = await admin.nestor.tasks.delegate("Analyse le dépôt", origin=TELEGRAM, requested_by=MATHIS)
        await asyncio.sleep(0.01)
        api = await admin.api("mathilde")
        listed = (await api.get("/api/v1/tasks")).json()
        assert [t["objective"] for t in listed["running"]] == ["Trouver un plombier"]
        assert (
            listed["running"][0]["status_label"] == "en cours"
            and listed["running"][0]["requested_by"]["id"] == "mathilde"
        )
        assert (await api.post(f"/api/v1/tasks/{his.id}/cancel")).status_code == 404
        stopped = (await api.post(f"/api/v1/tasks/{hers.id}/cancel")).json()
        assert stopped["confirmed"] and stopped["task"]["status"] == "cancelled"
        assert hers.status is TaskStatus.CANCELLED and his.status is TaskStatus.RUNNING
        assert [t["id"] for t in (await api.get("/api/v1/tasks")).json()["recent"]] == [hers.id]
        assert (await api.post(f"/api/v1/tasks/{hers.id}/cancel")).status_code == 404, "already ended"
        everything = (await (await admin.api()).get("/api/v1/tasks")).json()
        assert [t["id"] for t in everything["running"]] == [his.id]


async def test_a_stop_the_executor_does_not_confirm_is_reported(tmp_path: Path) -> None:
    async with Harness(tmp_path, confirms_stop=False) as admin:
        task = await admin.nestor.tasks.delegate("Long travail", origin=TELEGRAM)
        await asyncio.sleep(0.01)
        stopped = (await (await admin.api()).post(f"/api/v1/tasks/{task.id}/cancel")).json()
        assert stopped["confirmed"] is False and stopped["task"]["error"]


async def test_a_member_sees_and_cancels_their_own_watches_only(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        book = admin.nestor.watch_book
        hers = await book.create(Watch(what="le colis", keywords=("Colissimo",), owner=MATHILDE))
        his = await book.create(Watch(what="la facture", owner=MATHIS))
        api = await admin.api("mathilde")
        listed = (await api.get("/api/v1/watches")).json()
        assert [w["what"] for w in listed["watches"]] == ["le colis"] and listed["kinds"] == ["mail"]
        assert listed["watches"][0]["keywords"] == ["Colissimo"]
        assert (await api.post(f"/api/v1/watches/{his.id}/cancel")).status_code == 404
        assert (await api.post(f"/api/v1/watches/{hers.id}/cancel")).status_code == 204
        assert list(book.watches) == [his.id]


async def test_a_member_reads_memories_about_them_and_the_household_but_edits_only_theirs(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        memories = admin.nestor.memories
        hers = await memories.remember("Mathilde est végétarienne", about=MATHILDE)
        shared = await memories.remember("Le code du portail est 1234")
        his = await memories.remember("Mathis a un rendez-vous secret", about=MATHIS)
        api = await admin.api("mathilde")
        listed = {m["text"]: m["editable"] for m in (await api.get("/api/v1/memories")).json()}
        assert listed == {"Mathilde est végétarienne": True, "Le code du portail est 1234": False}
        found = (await api.get("/api/v1/memories", q="rendez-vous secret")).json()
        assert found == []
        assert (await api.get("/api/v1/memories", about="mathis")).status_code == 403

        assert (await api.patch(f"/api/v1/memories/{his.id}", {"text": "rien"})).status_code == 404
        assert (await api.delete(f"/api/v1/memories/{his.id}")).status_code == 404
        assert (await api.patch(f"/api/v1/memories/{shared.id}", {"text": "4321"})).status_code == 403
        corrected = await api.patch(f"/api/v1/memories/{hers.id}", {"text": "Mathilde est végane"})
        assert corrected.json()["text"] == "Mathilde est végane"
        assert (await api.patch(f"/api/v1/memories/{hers.id}", {"text": " "})).json()["error"]["code"] == "empty_memory"
        assert (await api.delete(f"/api/v1/memories/{hers.id}")).status_code == 204
        assert await memories.store.get(hers.id) is None and await memories.store.get(his.id) is not None


async def test_the_household_manages_every_memory(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        memory = await admin.nestor.memories.remember("Mathis aime le café", about=MATHIS, told_by=MATHIS)
        api = await admin.api()
        (listed,) = (await api.get("/api/v1/memories", q="café", about="mathis")).json()
        assert listed["about"] == {"id": "mathis", "name": "Mathis"} and listed["editable"]
        assert (await api.delete(f"/api/v1/memories/{memory.id}")).status_code == 204
        assert (await api.delete(f"/api/v1/memories/{memory.id}")).status_code == 404


async def test_the_household_lists_people_with_presence_connections_and_accounts(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        connections = admin.nestor.connections
        assert connections
        await connections.connect("imap", MATHIS, {"server": "s", "password": "p"})
        await connections.connect("imap", MATHILDE, {"server": "s", "password": "p"})
        people = {p["id"]: p for p in (await (await admin.api()).get("/api/v1/household/people")).json()}
        mathis = people["mathis"]
        assert mathis["presence"] == {"home": True, "room": "salon", "since": None} and mathis["reach"] == "memory:main"
        assert mathis["channel_accounts"] == ["memory:user"] and mathis["account"]["role"] == "owner"
        assert people["lucie"]["account"] is None and people["lucie"]["presence"] == {
            "home": None,
            "room": None,
            "since": None,
        }
        assert [len(p["connections"]) for p in people.values()] == [1, 1, 0]

        seen_by_member = {
            p["id"]: p for p in (await (await admin.api("mathilde")).get("/api/v1/household/people")).json()
        }
        assert seen_by_member["mathis"]["connections"] == [] and len(seen_by_member["mathilde"]["connections"]) == 1
        assert all(p["account"] is None for p in seen_by_member.values()), "accounts are for those who manage them"


async def test_without_a_presence_source_nobody_is_located(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        admin.nestor.presence = None
        people = (await (await admin.api()).get("/api/v1/household/people")).json()
        assert all(p["presence"] is None for p in people)


async def test_resources_say_where_they_come_from_and_what_became_of_them(tmp_path: Path) -> None:
    from nestor.modules.cognition.delegation.events import TaskDelivered
    from nestor.modules.cognition.tools import ToolCalled
    from nestor.modules.initiative import Delivered, WatchTriggered
    from nestor.modules.satellites import Device, Manifest, SatelliteConnected

    async with Harness(tmp_path) as admin:
        nestor = admin.nestor
        quick = await nestor.tasks.delegate("Vite fait", origin=TELEGRAM, requested_by=MATHIS)
        other = await nestor.tasks.delegate("Autre", origin=TELEGRAM, requested_by=MATHIS)
        await nestor.tasks.cancel(quick.id)
        await nestor.tasks.cancel(other.id)
        await nestor.journal.publish(TaskDelivered(source="tasks", task_id=quick.id, address=TELEGRAM))
        await nestor.journal.publish(
            Delivered(source="courier", address=Address("telegram", "9"), about=f"task {other.id} cancelled")
        )
        watch = await nestor.watch_book.create(Watch(what="le colis", owner=MATHIS, created_in=TELEGRAM))
        for item in ("i1", "i2"):
            await nestor.journal.publish(
                WatchTriggered(source="keeper", watch_id=watch.id, item_id=item, item_title="Colis", summary="")
            )
        memory = await nestor.memories.remember("Mathis aime le thé", about=MATHIS, source=TELEGRAM)
        assert nestor.connections
        connection = await nestor.connections.connect("imap", MATHIS, {"server": "s", "password": "p"})
        await nestor.journal.publish(
            ToolCalled(source="toolbox", address=TELEGRAM, call_id="c1", name="imap_search", arguments={})
        )
        await nestor.pairing.approve((await nestor.pairing.request(Manifest(Device("mic", "esp32", "bureau")))).code)
        await nestor.journal.publish(SatelliteConnected(source="voice", device_id="mic", room="bureau"))

        api = await admin.api()
        tasks = {t["id"]: t for t in (await api.get("/api/v1/tasks")).json()["recent"]}
        assert tasks[quick.id]["origin"] == {"session": "telegram:42", "channel": "telegram"}
        assert tasks[quick.id]["delivered"]["channel"] == "telegram" and tasks[quick.id]["delivered"]["room"] is None
        assert tasks[other.id]["delivered"]["channel"] == "telegram"
        (listed,) = (await api.get("/api/v1/watches")).json()["watches"]
        assert listed["triggered"] == 2 and listed["last_triggered_at"] and listed["origin"]["session"] == "telegram:42"
        (remembered,) = (await api.get("/api/v1/memories", q="thé")).json()
        assert remembered["session"] == "telegram:42" and remembered["learnt_event"]
        entry = (await api.get(f"/api/v1/journal/{remembered['learnt_event']}")).json()
        assert entry["item"]["links"]["memory"] == memory.id
        used = (await api.get(f"/api/v1/connections/{connection.id}")).json()
        assert used["calls_today"] == 1 and used["last_used_at"] and used["watches"] == 1
        (satellite,) = (await api.get("/api/v1/satellites")).json()["paired"]
        assert satellite["last_seen_at"] and satellite["sdk"] is None
