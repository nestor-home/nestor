"""The journal through the API: items already said in French, pages, facets, privacy between members,
and the live stream (Server-Sent Events) with its scopes, heartbeats and resumption."""

import asyncio
from pathlib import Path

import pytest

from nestor.admin.presentation import EventDescriber
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Role
from nestor.modules.channels import Address
from nestor.modules.conversation import AssistantTurn, UserTurn
from nestor.modules.initiative import DeliveryConsidered
from nestor.modules.memory import MemoryRecorded
from nestor.testing.satellites import pair_by_code

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
        (item,) = (await (await admin.api()).get("/api/v1/journal", kinds="delivery")).json()["items"]
        assert item["text"] == "Décision de parler à Mathis : veille w1"
        assert item["message"]["id"] == "journal-delivery-considered" and item["message"]["args"]["id"] == "w1"
        assert item["reason"] == {
            "message": {"id": "delivery-in-room", "args": {"person": "Mathis", "room": "salon"}},
            "text": "Mathis est dans la pièce « salon »",
        }
        assert item["tone"] == "decision" and item["links"]["delivery"] == "watch:w1" and item["links"]["watch"] == "w1"
        assert item["detail_text"] == "Prévu : à voix haute sur voice:salon" and item["detail"] == ""
        assert (item["kind"], item["kind_label"]) == ("delivery", "Prises de parole")
        assert item["people"] == [{"id": "mathis", "name": "Mathis"}] and item["channels"] == ["voice"]


async def test_sign_ins_are_in_the_journal_without_secrets(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await (await admin.api(None)).sign_in("mathis", "not the password")
        items = (await api.get("/api/v1/journal", kinds="account")).json()["items"]
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
                await api.get(
                    "/api/v1/journal", kinds="conversation", limit=3, **({"before": before} if before else {})
                )
            ).json()
            seen += [i["detail"] for i in page["items"]]
            before = page["next_before"]
            if before is None:
                break
        assert seen == [f"message {n}" for n in reversed(range(7))]
        assert (await api.get("/api/v1/journal", before=1)).json() == {"items": [], "next_before": None}


async def test_filters_keep_one_person_or_one_channel(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await conversations(admin)
        api = await admin.api()
        mathilde = (await api.get("/api/v1/journal", person="mathilde")).json()["items"]
        assert {i["detail"] for i in mathilde} == {"Rappelle-moi le dentiste", "Mathilde a peur des araignées"}
        assert len((await api.get("/api/v1/journal", channel="telegram")).json()["items"]) == 4
        unknown = await api.get("/api/v1/journal", kinds="gossip")
        assert unknown.status_code == 400 and unknown.json()["error"]["code"] == "unknown_kind"
        facets = (await api.get("/api/v1/journal/facets")).json()
        assert {"key": "conversation", "label": "Conversations", "count": 4} in facets["kinds"]
        assert facets["channels"] == [{"key": "telegram", "label": "telegram", "count": 4}]
        assert {"key": "mathilde", "label": "Mathilde", "count": 2} in facets["people"]


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
        async with EventStream(api, "/api/v1/journal/stream?kinds=conversation") as stream:
            await stream.frame()
            await admin.nestor.journal.publish(turn(MATHIS_CHAT, "un", "mathis"))
            last, _ = await stream.event()
        await admin.nestor.journal.publish(turn(MATHIS_CHAT, "deux", "mathis"))  # while disconnected
        await admin.nestor.journal.publish(turn(MATHIS_CHAT, "trois", "mathis"))
        async with EventStream(api, "/api/v1/journal/stream?kinds=conversation", Last_Event_ID=last) as stream:
            await stream.frame()
            assert [(await stream.event())[1]["detail"] for _ in range(2)] == ["deux", "trois"]
        async with EventStream(api, f"/api/v1/journal/stream?after={last}&kinds=conversation") as stream:
            await stream.frame()
            assert (await stream.event())[1]["detail"] == "deux"


async def test_the_live_stream_beats_while_idle_and_ends_with_its_session(tmp_path: Path) -> None:
    async with Harness(tmp_path, heartbeat_s=0.02) as admin:
        api = await admin.api()
        async with EventStream(api) as stream:
            await stream.frame()
            assert (await stream.activity())["state"] == "idle", "what the agent does comes first"
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
        assert user["links"]["session"] == "telegram:7" and user["kind"] == "conversation" and user["id"] == said.id
        assert (
            called["links"]["call"] == completed["links"]["call"] == "c1" and called["links"]["session"] == "telegram:7"
        )
        assert completed["links"]["session"] is None and completed["kind"] == "tool"
        assert called["tool"] == completed["tool"] == "light" and completed["outcome"] == {
            "ok": True,
            "duration_s": 0.1,
        }
        assert completed["cause"] == called["position"]
        assert (
            pairing["links"]["satellite"] == "mic-bureau"
            and pairing["kind"] == "satellite"
            and pairing["room"] == "bureau"
        )
        assert user["links"]["task"] is None and user["links"]["satellite"] is None


async def test_the_important_events_are_told_in_the_readers_language(tmp_path: Path) -> None:
    from nestor.core import Capability
    from nestor.modules.cognition import TaskEnded, TaskStarted, TaskStatus
    from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
    from nestor.modules.connectors import ConnectionChanged, Status
    from nestor.modules.conversation import AnswerCut, FallbackReason, FallbackSpoken
    from nestor.modules.home import PresenceChanged
    from nestor.modules.initiative import Delivered, DeliveryFailed, WatchCreated, WatchEnded, WatchTriggered
    from nestor.modules.memory import MemoryCorrected
    from nestor.modules.satellites import (
        DeclaredCapability,
        Device,
        Manifest,
        PersonDetected,
        SatelliteConnected,
        SatelliteDisconnected,
        SpeechActivityObserved,
    )

    mathis = PersonId("mathis")
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        reachy = Manifest(
            Device("reachy-salon", "reachy-mini", "salon"),
            tuple(DeclaredCapability(Capability(c)) for c in ("audio.capture", "audio.playback")),
        )
        await pair_by_code(pairing, reachy, by=mathis)
        await pairing.revoke("reachy-salon", by=mathis)
        for event in (
            AssistantTurn(source="agent", address=MATHIS_CHAT, text="Je surveille.", interrupted=True),
            FallbackSpoken(source="agent", address=MATHIS_CHAT, reason=FallbackReason.MODEL_SLOW),
            AnswerCut(source="agent", answer="t1", heard="Je surv"),
            ToolCalled(source="toolbox", address=MATHIS_CHAT, call_id="c1", name="create_watch", arguments={}),
            ToolCompleted(source="toolbox", call_id="c1", name="create_watch", output="ok", ok=True, duration_s=0.2),
            ToolCompleted(source="toolbox", call_id="c2", name="mailbox_send", output="no", ok=False, duration_s=1),
            WatchTriggered(
                source="keeper", watch_id="w1", item_id="i", item_title="Colis livré", summary="", urgent=True
            ),
            WatchEnded(source="watch-book", watch_id="w1", reason="matched"),
            Delivered(source="courier", address=MATHIS_CHAT, about="watch w1", person=mathis),
            DeliveryFailed(source="courier", about="watch w2", tried=(), person=mathis),
            MemoryCorrected(source="memory", memory_id="m1", text="Le chat s'appelle Biscotte"),
            PresenceChanged(source="presence", person=mathis, home=True, room="salon"),
            PresenceChanged(source="presence", person=mathis, home=False),
            PresenceChanged(source="presence", person=mathis, home=True),
            PresenceChanged(source="presence", person=PersonId("ghost"), home=None),
            TaskStarted(source="tasks", task_id="t1", objective="Analyse", executor="hermes", origin=MATHIS_CHAT),
            TaskEnded(source="tasks", task_id="t1", status=TaskStatus.FAILED, error="quota", duration_s=12),
            WatchCreated(
                source="watch-book", watch_id="w3", what="le colis", keywords=("Colissimo",), kinds=(), once=True
            ),
            ConnectionChanged(
                source="connections",
                connection_id="c1",
                status=Status.NEEDS_REAUTH,
                reason=Message.of("connection-refresh-refused"),
            ),
            SatelliteConnected(source="voice", device_id="reachy-salon", room="salon"),
            SatelliteDisconnected(source="voice", device_id="reachy-salon", room="salon"),
            PersonDetected(source="voice", device_id="reachy-salon", room="salon", count=2, confidence=0.87),
            PersonDetected(source="voice", device_id="reachy-salon", room="salon", count=1, confidence=0.5),
            SpeechActivityObserved(source="voice", device_id="reachy-salon", room="salon", active=True),
            SpeechActivityObserved(source="voice", device_id="reachy-salon", room="salon", active=False),
            turn(MATHIS_CHAT, "bla " * 400, "mathis"),
        ):
            await admin.nestor.journal.publish(event)
        found = (await (await admin.api()).get("/api/v1/journal", limit=200)).json()["items"]
        said = "\n".join(f"{i['text']}\n{i['detail_text']}" for i in found)
        for sentence in (
            "Richie a répondu (interrompu)",
            "Réponse de secours : modèle trop lent",
            "Réponse coupée par la personne",
            "Entendu : Je surv",
            "Outil create_watch appelé",
            "Outil create_watch terminé en 0,2 s",
            "Outil mailbox_send en échec",
            "Veille w1 déclenchée par « Colis livré » (urgent)",
            "Veille w1 trouvée",
            "Message transmis : veille w1",
            "Message non transmis : veille w2",
            "Essayé : aucun canal disponible",
            "Souvenir corrigé",
            "Mathis est dans la pièce « salon »",
            "Mathis n'est plus à la maison",
            "Mathis est à la maison",
            "ghost n'est plus localisé·e",
            "Tâche t1 confiée à hermes",
            "Tâche t1 en échec (12 s)",
            "Mots-clés : Colissimo",
            "Connexion c1 à réautoriser",
            "Le satellite reachy-salon (reachy-mini, pièce « salon ») demande l'appairage",
            "Déclare : micro, haut-parleur",
            "Satellite reachy-salon appairé avec son code (pièce « salon »)",
            "Autorisé : micro, haut-parleur",
            "Satellite reachy-salon révoqué",
            "Satellite reachy-salon connecté",
            "Satellite reachy-salon déconnecté",
            "2 personnes vues par reachy-salon",
            "Confiance : 87\N{NO-BREAK SPACE}%",
            "1 personne vue par reachy-salon",
            "Parole détectée près de reachy-salon",
            "Fin de parole près de reachy-salon",
            "bla …",
        ):
            assert sentence in said, sentence
        interrupted = next(i for i in found if i["detail"] == "Je surveille.")
        assert interrupted["message"]["id"] == "journal-assistant-interrupted"
        assert {i["room"] for i in found if i["kind"] == "observation"} == {"salon"}


async def test_going_back_to_the_households_language_is_told_and_never_breaks_the_journal(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await api.put("/api/v1/me/locale", {"locale": "en"})
        await api.put("/api/v1/me/locale", {"locale": None})
        page = await api.get("/api/v1/journal", kinds="account")
        assert page.status_code == 200, page.text
        reset, chosen = page.json()["items"][:2]
        assert reset["text"] == "Le compte mathis lit désormais dans la langue du foyer"
        assert reset["message"] == {
            "id": "journal-account-locale-changed",
            "args": {"login": "mathis", "role": "owner", "locale": "", "chosen": "no"},
        }
        assert chosen["text"] == "Le compte mathis lit désormais en en"
        facets = await api.get("/api/v1/journal/facets")
        assert facets.status_code == 200 and facets.json()["total"] >= 4


async def test_an_entry_that_cannot_be_described_shows_its_type_and_the_rest_still_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: EventDescriber, event: UserTurn) -> None:
        raise RuntimeError("a bug in one describer")

    monkeypatch.setattr(EventDescriber, "_user_turn", broken)
    async with Harness(tmp_path) as admin:
        await conversations(admin)
        api = await admin.api()
        page = await api.get("/api/v1/journal", kinds="conversation")
        assert page.status_code == 200, page.text
        items = page.json()["items"]
        said = [i for i in items if i["type"] == UserTurn.event_type]
        assert {i["text"] for i in said} == {"conversation.turn.user"}
        assert all(i["kind"] == "conversation" and i["tone"] == "warning" for i in said)
        assert "Il est midi." in {i["detail"] for i in items}, "the entries around it read as usual"
        assert (await api.get("/api/v1/journal/facets")).status_code == 200
