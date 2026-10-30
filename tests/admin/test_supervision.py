"""Supervising the assistant: why it spoke, its tasks and watches, what it remembers, who it serves."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nestor.admin.presentation import french_reason, french_subject, french_time
from nestor.core import PersonId
from nestor.modules.channels import Address, Medium
from nestor.modules.cognition import TaskEnded, TaskStarted, TaskStatus
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.connectors import ConnectionChanged, Status
from nestor.modules.conversation import AnswerCut, AssistantTurn, FallbackReason, FallbackSpoken, UserTurn
from nestor.modules.home import Granularity, PresenceChanged
from nestor.modules.household import Person
from nestor.modules.initiative import (
    Delivered,
    DeliveryConsidered,
    DeliveryFailed,
    DeliveryPolicy,
    QuietHours,
    Watch,
    WatchCreated,
    WatchEnded,
    WatchTriggered,
)
from nestor.modules.memory import MemoryCorrected
from nestor.testing.channels import InMemoryChannel
from nestor.testing.home import StaticPresence

from .harness import Harness

MATHIS = PersonId("mathis")
TELEGRAM = Address("telegram", "42")
NOON = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)


class Satellite(InMemoryChannel):
    medium = Medium.SPOKEN

    def __init__(self, channel_id: str, room: str) -> None:
        super().__init__(channel_id)
        self.room = room


def plans() -> list[str]:
    """Every reason the real delivery policy gives, so a new wording shows up here."""
    person = Person(id=MATHIS, name="Mathis", reach=Address("telegram", "main"))
    channels = [Satellite("voice", "salon"), InMemoryChannel("telegram")]
    presences = [
        StaticPresence().set("mathis", home=False),
        StaticPresence(Granularity.PERSON_ROOM).set("mathis", home=True, room="salon"),
        StaticPresence(Granularity.PERSON_ROOM).set("mathis", home=True, room="garage"),
        StaticPresence().set("mathis", home=True),
        StaticPresence().set("mathis", home=None),
    ]
    policy = DeliveryPolicy(main_room="salon")
    reasons = [
        DeliveryPolicy().plan(person, channels=channels, presence=None, origin=None, now=NOON).reason,
        policy.plan(person, channels=channels, presence=None, origin=None, now=NOON, written=True).reason,
        DeliveryPolicy(quiet_hours=QuietHours.parse("00:00-23:59"))
        .plan(person, channels=channels, presence=presences[0].presence(), origin=None, now=NOON)
        .reason,
        DeliveryPolicy()
        .plan(person, channels=channels, presence=presences[3].presence(), origin=None, now=NOON)
        .reason,
    ]
    reasons += [
        policy.plan(person, channels=channels, presence=p.presence(), origin=None, now=NOON).reason for p in presences
    ]
    return sorted(set(reasons))


@pytest.mark.parametrize("reason", plans())
def test_every_delivery_reason_of_the_policy_is_said_in_french(reason: str) -> None:
    said = french_reason(reason)
    assert said != reason
    assert not any(word in said.split() for word in ("is", "the", "no", "away", "home,"))


def test_delivery_subjects_are_said_in_french_and_unknown_ones_kept() -> None:
    assert french_subject("task 3f2a1c completed") == "tâche 3f2a1c terminée"
    assert french_subject("watch 9d81 (follow-up)") == "veille 9d81 (relance)"
    assert french_subject("anniversaire") == "anniversaire"
    assert french_reason("a reason nobody wrote yet") == "a reason nobody wrote yet"


def test_dates_are_said_the_french_way_in_the_assistants_timezone() -> None:
    assert french_time(NOON, "Europe/Paris", now=NOON) == "aujourd'hui 12:00"
    assert french_time(NOON - timedelta(days=2), "Europe/Paris", now=NOON) == "28 oct. 12:00"
    assert french_time(NOON - timedelta(days=365), "Europe/Paris", now=NOON) == "30 oct. 2025 12:00"


async def test_the_journal_says_why_the_assistant_spoke_in_french(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        person = admin.nestor.household.person(MATHIS)
        plan = admin.nestor.courier.policy.plan(
            person,
            channels=admin.nestor.channels,
            presence=StaticPresence().set("mathis", home=False).presence(),
            origin=None,
            now=NOON,
        )
        await admin.nestor.journal.publish(
            DeliveryConsidered(
                source="courier", about="task 3f2a1c completed", reason=plan.reason, written=plan.written, person=MATHIS
            )
        )
        page = (await admin.get("/journal")).text
        assert "Mathis n&#39;est pas à la maison" in page
        assert "Décision de parler à Mathis — tâche 3f2a1c terminée" in page
        assert "is away" not in page


async def test_the_journal_tells_the_important_events_in_french(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        journal = admin.nestor.journal
        events = [
            UserTurn(source="agent", address=TELEGRAM, text="Préviens-moi pour le colis", person=MATHIS),
            AssistantTurn(source="agent", address=TELEGRAM, text="Je surveille.", interrupted=True),
            FallbackSpoken(source="agent", address=TELEGRAM, reason=FallbackReason.MODEL_SLOW),
            AnswerCut(source="agent", turn="t1", heard="Je surv"),
            ToolCalled(
                source="toolbox", address=TELEGRAM, call_id="c1", name="create_watch", arguments={"what": "colis"}
            ),
            ToolCompleted(source="toolbox", call_id="c1", name="create_watch", output="ok", ok=True, duration_s=0.2),
            ToolCompleted(
                source="toolbox", call_id="c2", name="mailbox_send", output="refused", ok=False, duration_s=1
            ),
            WatchTriggered(
                source="watch-keeper", watch_id="w1", item_id="i", item_title="Colis livré", summary="", urgent=True
            ),
            WatchEnded(source="watch-book", watch_id="w1", reason="matched"),
            Delivered(source="courier", address=TELEGRAM, about="watch w1", person=MATHIS),
            DeliveryFailed(source="courier", about="watch w2", tried=(), person=MATHIS),
            MemoryCorrected(source="memory", memory_id="m1", text="Le chat s'appelle Biscotte"),
            PresenceChanged(source="presence", person=MATHIS, home=True, room="salon"),
            PresenceChanged(source="presence", person=MATHIS, home=False),
            PresenceChanged(source="presence", person=MATHIS, home=True),
            PresenceChanged(source="presence", person=PersonId("ghost"), home=None),
            TaskStarted(source="tasks", task_id="t1", objective="Analyse", executor="hermes", origin=TELEGRAM),
            TaskEnded(source="tasks", task_id="t1", status=TaskStatus.FAILED, error="quota", duration_s=12),
            DeliveryConsidered(
                source="courier", about="watch w1", reason="Mathis is in the salon", spoken=Address("voice", "salon")
            ),
            WatchCreated(
                source="watch-book", watch_id="w3", what="le colis", keywords=("Colissimo",), kinds=(), once=True
            ),
            ConnectionChanged(source="connections", connection_id="c1", status=Status.NEEDS_REAUTH, reason="refused"),
            UserTurn(source="agent", address=TELEGRAM, text="bla " * 400),
        ]
        for event in events:
            await journal.publish(event)
        page = (await admin.get("/journal")).text
        for said in (
            "Mathis a dit",
            "Richie a répondu (interrompu)",
            "Réponse de secours : modèle trop lent",
            "Réponse coupée par la personne",
            "Outil create_watch appelé",
            "Outil create_watch terminé en 0.2 s",
            "Outil mailbox_send en échec",
            "Veille w1 déclenchée par « Colis livré » — urgent",
            "Veille w1 trouvée",
            "Message transmis — veille w1",
            "Message non transmis — veille w2",
            "Souvenir corrigé",
            "Mathis est dans la pièce « salon »",
            "Mathis n&#39;est plus à la maison",
            "Mathis est à la maison",
            "ghost n&#39;est plus localisé·e",
            "Tâche t1 confiée à hermes",
            "Tâche t1 en échec (12 s)",
            "Prévu : à voix haute sur voice:salon",
            "Mots-clés : Colissimo",
            "Connexion c1 à réautoriser",
            "bla …",
        ):
            assert said in page, said


async def test_the_journal_filters_by_type_person_and_channel(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        journal = admin.nestor.journal
        await journal.publish(UserTurn(source="agent", address=TELEGRAM, text="message de Mathis", person=MATHIS))
        await journal.publish(UserTurn(source="agent", address=Address("voice", "salon"), text="message vocal"))
        await admin.nestor.memories.remember("souvenir de Mathilde", about=PersonId("mathilde"))

        by_type = (await admin.get("/journal", type="memory")).text
        assert "souvenir de Mathilde" in by_type and "message de Mathis" not in by_type
        by_person = (await admin.get("/journal", person="mathilde")).text
        assert "souvenir de Mathilde" in by_person and "message vocal" not in by_person
        by_channel = (await admin.get("/journal", channel="voice")).text
        assert "message vocal" in by_channel and "message de Mathis" not in by_channel
        assert "Rien dans le journal" in (await admin.get("/journal", channel="nowhere")).text
        assert "message vocal" in (await admin.get("/journal", before="not a date")).text


async def test_the_journal_pages_back_in_time(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        for n in range(101):
            await admin.nestor.journal.publish(UserTurn(source="agent", address=TELEGRAM, text=f"message n°{n}"))
        first = (await admin.get("/journal")).text
        assert "message n°100" in first and "message n°0<" not in first and "Plus ancien" in first
        older = first.split('href="/journal?')[1].split('"')[0].replace("&amp;", "&")
        second = (await admin.browser.get(f"/journal?{older}")).text
        assert "message n°0<" in second and "message n°100" not in second


async def test_an_event_no_installed_code_knows_is_still_listed(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        payload = json.dumps({"x": 1})
        await admin.nestor.database.write(
            lambda c: c.execute(
                "INSERT INTO events (id, type, version, at, source, session, payload) "
                "VALUES (?, ?, 1, ?, 's', NULL, ?)",
                ("e1", "plugin.gone", "2026-10-30T10:00:00.000000Z", payload),
            )
        )
        assert "plugin.gone" in (await admin.get("/journal")).text


async def test_a_running_task_is_listed_and_can_be_stopped(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        task = await admin.nestor.tasks.delegate("Analyse le dépôt", origin=TELEGRAM, requested_by=MATHIS)
        await asyncio.sleep(0.01)
        page = (await admin.get("/tasks")).text
        assert "Analyse le dépôt" in page and "Arrêter" in page and "par Mathis" in page

        response = await admin.post(f"/tasks/{task.id}/cancel")
        assert response.headers["location"] == "/tasks"
        assert task.status is TaskStatus.CANCELLED
        page = (await admin.get("/tasks")).text
        assert f"Tâche {task.id} arrêtée" in page and "annulée" in page and "Aucune tâche en cours" in page
        assert (await admin.post(f"/tasks/{task.id}/cancel")).status_code == 404


async def test_a_stop_the_executor_does_not_confirm_is_reported(tmp_path: Path) -> None:
    async with Harness(tmp_path, confirms_stop=False) as admin:
        await admin.login()
        task = await admin.nestor.tasks.delegate("Long travail", origin=TELEGRAM)
        await asyncio.sleep(0.01)
        await admin.get("/tasks")
        await admin.post(f"/tasks/{task.id}/cancel")
        assert "sans confirmation" in (await admin.get("/tasks")).text


async def test_an_active_watch_can_be_cancelled(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        book = admin.nestor.watch_book
        watch = await book.create(
            Watch(
                what="le colis de la poussette", keywords=("Colissimo",), owner=MATHIS, until=NOON + timedelta(days=9)
            )
        )
        page = (await admin.get("/watches")).text
        assert "le colis de la poussette" in page and "Colissimo" in page and "Pour Mathis" in page
        assert "Sources disponibles : mail" in page, "the connectors' inbound kinds can be watched"

        response = await admin.post(f"/watches/{watch.id}/cancel")
        assert response.headers["location"] == "/watches"
        assert book.watches == {}
        assert (await admin.nestor.journal.history(WatchEnded))[-1].reason == "cancelled"
        assert "Aucune veille active" in (await admin.get("/watches")).text
        assert (await admin.post(f"/watches/{watch.id}/cancel")).status_code == 404


async def test_memories_are_searched_corrected_and_forgotten(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        memories = admin.nestor.memories
        cat = await memories.remember("Le chat s'appelle Biscote", about=MATHIS, told_by=MATHIS, source=TELEGRAM)
        await memories.remember("Mathilde aime le thé", about=PersonId("mathilde"))

        assert "Biscote" in (await admin.get("/memories")).text
        found = (await admin.get("/memories", q="chat")).text
        assert "Biscote" in found and "thé" not in found
        about = (await admin.get("/memories", about="mathilde")).text
        assert "thé" in about and "Biscote" not in about

        await admin.post(
            f"/memories/{cat.id}/correct", {"text": "Le chat s'appelle Biscotte", "back": "/memories?q=chat"}
        )
        assert [m.text for m in await memories.recall("chat")] == ["Le chat s'appelle Biscotte"]
        empty = await admin.post(f"/memories/{cat.id}/correct", {"text": "  "})
        assert empty.status_code == 400

        response = await admin.post(f"/memories/{cat.id}/forget", {"back": "https://evil.example"})
        assert response.headers["location"] == "/memories"
        assert await memories.recall("chat") == []
        assert "Souvenir oublié" in (await admin.get("/memories")).text
        assert (await admin.post(f"/memories/{cat.id}/forget")).status_code == 404
        assert (await admin.post(f"/memories/{cat.id}/correct", {"text": "x"})).status_code == 404
        assert "Aucun souvenir ne correspond" in (await admin.get("/memories", q="chat")).text


async def test_the_household_page_shows_people_presence_and_their_accounts(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        assert admin.nestor.connections
        await admin.nestor.connections.connect("imap", PersonId("mathilde"), {"server": "s", "password": "p"})
        page = (await admin.get("/people")).text
        assert "Mathis" in page and "memory:user" in page and "À la maison (salon)" in page
        assert "mathilde@free.fr" in page
