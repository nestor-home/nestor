"""The journal through the API: items already said in French, pages, filters, privacy between members,
and the live stream (Server-Sent Events) with its scopes, heartbeats and resumption."""

import asyncio
from pathlib import Path

from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Role
from nestor.modules.channels import Address
from nestor.modules.conversation import AssistantTurn, UserTurn
from nestor.modules.initiative import DeliveryConsidered
from nestor.modules.memory import MemoryRecorded

from ...harness import EventStream, Harness

MATHIS_CHAT, MATHILDE_CHAT = Address("telegram", "7"), Address("telegram", "42")


def turn(address: Address, text: str, person: str | None) -> UserTurn:
    return UserTurn(
        source="agent", session=address.session, address=address, text=text, person=PersonId(person) if person else None
    )


def answer(address: Address, text: str) -> AssistantTurn:
    return AssistantTurn(source="agent", session=address.session, address=address, text=text)


async def conversations(admin: Harness) -> None:
    for event in (
        turn(MATHIS_CHAT, "Quelle heure est-il ?", "mathis"),
        answer(MATHIS_CHAT, "Il est midi."),
        turn(MATHILDE_CHAT, "Rappelle-moi le dentiste", "mathilde"),
        answer(MATHILDE_CHAT, "C'est noté."),
        MemoryRecorded(
            source="memory", memory_id="m1", text="Mathilde a peur des araignées", about=PersonId("mathilde")
        ),
    ):
        await admin.nestor.journal.publish(event)


async def test_items_are_said_in_french_with_the_reason_of_a_decision(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.nestor.journal.publish(
            DeliveryConsidered(
                source="courier",
                about="watch w1",
                reason=Message.of("delivery-in-room", person="Mathis", room="salon"),
                spoken=Address("voice", "salon"),
                person=PersonId("mathis"),
            )
        )
        (item,) = (await (await admin.api()).get("/api/v1/journal", kind="delivery")).json()["items"]
        assert item["text"] == "Décision de parler à Mathis — veille w1"
        assert item["message"]["id"] == "journal-delivery-considered" and item["message"]["args"]["id"] == "w1"
        assert item["reason"] == {"id": "delivery-in-room", "args": {"person": "Mathis", "room": "salon"}}
        assert item["reason_text"] == "Mathis est dans la pièce « salon »" and item["tone"] == "decision"
        assert item["detail_text"] == "Prévu : à voix haute sur voice:salon" and item["detail"] == ""
        assert (item["kind"], item["kind_label"]) == ("delivery", "Prises de parole")
        assert item["people"] == [{"id": "mathis", "name": "Mathis"}] and item["channels"] == ["voice"]


async def test_sign_ins_are_in_the_journal_without_secrets(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await (await admin.api(None)).sign_in("mathis", "not the password")
        items = (await api.get("/api/v1/journal", kind="account")).json()["items"]
        summaries = [i["text"] for i in items]
        assert summaries[:3] == [
            "Connexion refusée au compte mathis : mot de passe incorrect",
            "Connexion de mathis",
            "Compte mathis ouvert (propriétaire)",
        ]


async def test_pages_go_back_in_time_without_gaps_or_repeats(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for n in range(7):
            await admin.nestor.journal.publish(turn(MATHIS_CHAT, f"message {n}", "mathis"))
        api = await admin.api()
        seen, before = [], None
        while True:
            page = (
                await api.get("/api/v1/journal", kind="conversation", limit=3, **({"before": before} if before else {}))
            ).json()
            seen += [i["detail"] for i in page["items"]]
            before = page["next_before"]
            if before is None:
                break
        assert seen == [f"message {n}" for n in reversed(range(7))]
        assert (await api.get("/api/v1/journal", before=10**9)).json() == {"items": [], "next_before": None}


async def test_filters_keep_one_person_or_one_channel(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await conversations(admin)
        api = await admin.api()
        mathilde = (await api.get("/api/v1/journal", person="mathilde")).json()["items"]
        assert {i["detail"] for i in mathilde} == {"Rappelle-moi le dentiste", "Mathilde a peur des araignées"}
        assert len((await api.get("/api/v1/journal", channel="telegram")).json()["items"]) == 4
        unknown = await api.get("/api/v1/journal", kind="gossip")
        assert unknown.status_code == 400 and unknown.json()["error"]["code"] == "unknown_kind"
        filters = (await api.get("/api/v1/journal/filters")).json()
        assert {"key": "account", "label": "Comptes"} in filters["kinds"]
        assert filters["channels"] == [{"id": "telegram", "brand": None}]
        assert filters["people"][0] == {"id": "mathis", "name": "Mathis"}


async def test_a_member_reads_their_own_conversations_not_another_members(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        await conversations(admin)
        items = (await (await admin.api("mathilde")).get("/api/v1/journal")).json()["items"]
        details = {i["detail"] for i in items}
        assert {"Rappelle-moi le dentiste", "C'est noté.", "Mathilde a peur des araignées"} <= details
        assert "Quelle heure est-il ?" not in details and "Il est midi." not in details
        assert "Connexion de mathis" not in {i["text"] for i in items}
        everything = (await (await admin.api()).get("/api/v1/journal")).json()["items"]
        assert "Il est midi." in {i["detail"] for i in everything}


async def test_the_live_stream_sends_new_entries_with_their_position(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        async with EventStream(api) as stream:
            assert await stream.frame() == "retry: 3000"
            await admin.nestor.journal.publish(turn(MATHIS_CHAT, "Bonjour", "mathis"))
            position, item = await stream.event()
            assert stream.status == 200 and item["text"] == "Mathis a dit" and item["detail"] == "Bonjour"
            assert int(position) == item["position"]


async def test_the_live_stream_respects_the_readers_scopes(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        async with EventStream(await admin.api("mathilde")) as stream:
            await stream.frame()
            await conversations(admin)
            received = [(await stream.event())[1]["detail"] for _ in range(3)]
            assert received == ["Rappelle-moi le dentiste", "C'est noté.", "Mathilde a peur des araignées"]


async def test_the_live_stream_resumes_after_the_last_event_it_sent(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        async with EventStream(api, "/api/v1/journal/stream?kind=conversation") as stream:
            await stream.frame()
            await admin.nestor.journal.publish(turn(MATHIS_CHAT, "un", "mathis"))
            last, _ = await stream.event()
        await admin.nestor.journal.publish(turn(MATHIS_CHAT, "deux", "mathis"))  # while disconnected
        await admin.nestor.journal.publish(turn(MATHIS_CHAT, "trois", "mathis"))
        async with EventStream(api, "/api/v1/journal/stream?kind=conversation", Last_Event_ID=last) as stream:
            await stream.frame()
            assert [(await stream.event())[1]["detail"] for _ in range(2)] == ["deux", "trois"]
        async with EventStream(api, f"/api/v1/journal/stream?after={last}&kind=conversation") as stream:
            await stream.frame()
            assert (await stream.event())[1]["detail"] == "deux"


async def test_the_live_stream_beats_while_idle_and_ends_with_its_session(tmp_path: Path) -> None:
    async with Harness(tmp_path, heartbeat_s=0.02) as admin:
        api = await admin.api()
        async with EventStream(api) as stream:
            await stream.frame()
            assert await stream.frame() == ": heartbeat"
            assert admin.owner
            admin.app.state.admin.sessions.revoke(admin.owner.id)
            await asyncio.wait_for(stream.ended.wait(), 1)


async def test_the_live_stream_ends_when_the_server_stops(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin, EventStream(await admin.api()) as stream:
        await stream.frame()
        admin.app.state.admin.closing.set()
        await asyncio.wait_for(stream.ended.wait(), 1)


async def test_the_live_stream_refuses_who_may_not_read(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        async with EventStream(await admin.api(None)) as stream:
            await asyncio.wait_for(stream.ended.wait(), 1)
        assert stream.status == 401


async def test_items_carry_the_ids_that_link_them_into_threads(tmp_path: Path) -> None:
    from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
    from nestor.modules.satellites import Device, Manifest

    async with Harness(tmp_path) as admin:
        journal = admin.nestor.journal
        said = turn(MATHIS_CHAT, "Allume la lumière", "mathis")
        await journal.publish(said)
        await journal.publish(
            ToolCalled(
                source="toolbox", session=said.session, address=MATHIS_CHAT, call_id="c1", name="light", arguments={}
            )
        )
        await journal.publish(
            ToolCompleted(source="toolbox", call_id="c1", name="light", output="ok", ok=True, duration_s=0.1)
        )
        await admin.nestor.pairing.request(Manifest(Device("mic-bureau", "esp32", "bureau")))
        items = {i["type"]: i for i in (await (await admin.api()).get("/api/v1/journal")).json()["items"]}
        user, called = items["conversation.turn.user"], items["agent.tool.called"]
        completed, pairing = items["agent.tool.completed"], items["satellite.pairing.requested"]
        assert user["session"] == "telegram:7" and user["kind"] == "conversation" and user["id"] == said.id
        assert called["call_id"] == completed["call_id"] == "c1" and called["session"] == "telegram:7"
        assert completed["session"] is None and completed["kind"] == "tool"
        assert pairing["device_id"] == "mic-bureau" and pairing["pairing_id"] and pairing["kind"] == "satellite"
        assert user["task_id"] is None and user["device_id"] is None
