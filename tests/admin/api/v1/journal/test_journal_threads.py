"""The journal as threads: causes chaining entries, every filter, facets that
ignore their own selection, one entry with its record — and sign-in only from the admin's own pages."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from nestor.core import PersonId, new_id, utc_now
from nestor.core.i18n import Message
from nestor.modules.accounts import Role
from nestor.modules.channels import Address, Exchange, InboundMessage, Medium, Sender
from nestor.modules.cognition import TaskEnded, TaskStarted, TaskStatus
from nestor.modules.cognition.delegation.events import TaskDelivered
from nestor.modules.conversation import AssistantTurn, Conversations, NotificationTurn, UserTurn
from nestor.modules.home import PresenceChanged
from nestor.modules.identity import Speaker
from nestor.modules.initiative import Delivered, DeliveryConsidered, WatchCreated, WatchTriggered
from nestor.modules.memory import MemoryRecorded

from ....harness import OWNER, PASSWORD, Api, Harness

TELEGRAM, VOICE = Address("telegram", "7"), Address("voice", "salon")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")
REASON = Message.of("delivery-in-room", person="Mathis", room="salon")


async def items(api: Api, **params: Any) -> list[dict[str, Any]]:
    response = await api.get("/api/v1/journal", limit=200, **params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def by_type(found: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in reversed(found):  # oldest first
        grouped.setdefault(item["type"], []).append(item)
    return grouped


async def test_a_watch_chains_to_its_delivery_and_its_follow_up(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for event in (
            WatchCreated(source="watch-book", watch_id="w1", what="le colis", kinds=("mail",), once=True),
            WatchTriggered(source="watch-keeper", watch_id="w1", item_id="i1", item_title="Colis", summary=""),
            DeliveryConsidered(source="courier", about="watch w1", reason=REASON, spoken=VOICE, person=MATHIS),
            Delivered(source="courier", address=VOICE, about="watch w1", person=MATHIS),
            DeliveryConsidered(source="courier", about="watch w1 (follow-up)", reason=REASON, written=TELEGRAM),
            Delivered(source="courier", address=TELEGRAM, about="watch w1 (follow-up)", person=MATHIS),
        ):
            await admin.nestor.journal.publish(event)
        found = by_type(await items(await admin.api(), watch="w1"))
        created, triggered = found["watch.created"][0], found["watch.triggered"][0]
        considered, follow_up = found["initiative.considered"]
        delivered, followed = found["initiative.delivered"]
        assert triggered["cause"] == created["position"]
        assert considered["cause"] == triggered["position"]
        assert delivered["cause"] == considered["position"]
        assert follow_up["cause"] == delivered["position"], "a follow-up is caused by the first delivery"
        assert followed["cause"] == follow_up["position"]
        assert considered["message"]["args"]["follow_up"] == "no" and follow_up["message"]["args"]["follow_up"] == "yes"
        assert {i["links"]["delivery"] for i in (considered, delivered, follow_up, followed)} == {"watch:w1"}


async def test_a_task_chains_from_its_start_to_its_result(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for event in (
            TaskStarted(source="tasks", task_id="t1", objective="Analyse", executor="hermes", origin=TELEGRAM),
            TaskEnded(source="tasks", task_id="t1", status=TaskStatus.COMPLETED, result="ok", duration_s=12),
            DeliveryConsidered(source="courier", about="task t1 completed", reason=REASON, written=TELEGRAM),
            TaskDelivered(source="tasks", task_id="t1", address=TELEGRAM),
        ):
            await admin.nestor.journal.publish(event)
        found = by_type(await items(await admin.api(), task="t1"))
        started, ended = found["task.started"][0], found["task.ended"][0]
        assert ended["cause"] == started["position"] and ended["outcome"] == {"ok": True, "duration_s": 12.0}
        assert found["initiative.considered"][0]["cause"] == ended["position"]
        assert found["task.delivered"][0]["cause"] == ended["position"]
        assert started["cause"] is None


async def test_an_unprompted_message_chains_from_its_delivery_through_its_cue(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        turn = Exchange(conversation_id="c1", turn_id="t1")
        for event in (
            DeliveryConsidered(source="courier", about="task t1 completed", reason=REASON, written=TELEGRAM),
            NotificationTurn(
                source="agent",
                session=TELEGRAM.session,
                address=TELEGRAM,
                text="Result: ok",
                about="task t1 completed",
                exchange=turn,
                person=PersonId("mathis"),
            ),
            AssistantTurn(
                source="agent", session=TELEGRAM.session, address=TELEGRAM, text="C'est fait.", exchange=turn
            ),
        ):
            await admin.nestor.journal.publish(event)
        found = by_type(await items(await admin.api()))
        considered, notification = found["initiative.considered"][0], found["conversation.turn.notification"][0]
        answered = found["conversation.turn.assistant"][0]
    assert notification["cause"] == considered["position"] and answered["cause"] == notification["position"]
    assert notification["text"] == "Pour Richie : tâche t1 terminée" and notification["detail"] == "Result: ok"


async def test_every_filter_narrows_the_journal(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        journal = admin.nestor.journal
        await journal.publish(
            UserTurn(
                medium=Medium.WRITTEN,
                exchange=Exchange(conversation_id="c1", turn_id=new_id()),
                source="agent",
                session=TELEGRAM.session,
                address=TELEGRAM,
                text="Le dentiste",
                speaker=Speaker.account(MATHIS),
            )
        )
        await journal.publish(
            UserTurn(
                medium=Medium.WRITTEN,
                exchange=Exchange(conversation_id="c1", turn_id=new_id()),
                source="agent",
                session=VOICE.session,
                address=VOICE,
                text="Bonsoir",
                speaker=Speaker.account(MATHILDE),
            )
        )
        await journal.publish(PresenceChanged(source="presence", person=MATHIS, home=True, room="cuisine"))
        await journal.publish(DeliveryConsidered(source="courier", about="watch w9", reason=REASON, person=MATHIS))
        await journal.publish(MemoryRecorded(source="memory", memory_id="m1", text="Aime le thé", about=MATHILDE))
        api = await admin.api()

        def details(found: list[dict[str, Any]]) -> set[str]:
            return {i["detail"] or i["text"] for i in found}

        assert details(await items(api, q="DENTISTE")) == {"Le dentiste"}
        assert {i["type"] for i in await items(api, q="pièce « salon »")} == {"initiative.considered"}, "reasons count"
        assert {i["type"] for i in await items(api, q="a dit")} == {"conversation.turn.user"}, "rendered text counts"
        assert {i["room"] for i in await items(api, room="cuisine")} == {"cuisine"}
        assert details(await items(api, session="telegram:7")) == {"Le dentiste"}
        assert details(await items(api, channel="telegram")) == {"Le dentiste"}
        assert details(await items(api, person="mathilde")) == {"Bonsoir", "Aime le thé"}, "memories about them too"
        assert {i["tone"] for i in await items(api, tone="decision")} == {"decision"}
        assert details(await items(api, kinds=["conversation", "presence"], person="mathilde")) == {"Bonsoir"}
        assert await items(api, **{"from": (utc_now() + timedelta(hours=1)).isoformat()}) == []
        assert len(await items(api, to=(utc_now() + timedelta(hours=1)).isoformat(), kinds="conversation")) == 2
        refused = (await api.get("/api/v1/journal", kinds=["conversation", "gossip"])).json()["error"]
        assert (refused["code"], refused["args"]) == ("invalid_request", {"fields": "kinds.1"})


async def test_each_facet_is_counted_ignoring_its_own_selection(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        journal = admin.nestor.journal
        for text, person, address in (("a", MATHIS, TELEGRAM), ("b", MATHIS, TELEGRAM), ("c", MATHILDE, VOICE)):
            await journal.publish(
                UserTurn(
                    medium=Medium.WRITTEN,
                    exchange=Exchange(conversation_id="c1", turn_id=new_id()),
                    source="agent",
                    address=address,
                    text=text,
                    speaker=Speaker.account(person),
                )
            )
        await journal.publish(PresenceChanged(source="presence", person=MATHIS, home=True, room="salon"))
        api = await admin.api()
        facets = (await api.get("/api/v1/journal/facets", kinds="conversation", person="mathis")).json()
        assert facets["total"] == 2 and not facets["truncated"]
        kinds = {f["key"]: f["count"] for f in facets["kinds"]}
        assert kinds["conversation"] == 2 and kinds["presence"] == 1, "kinds counted for mathis, whatever the kind"
        people = {f["key"]: f["count"] for f in facets["people"]}
        assert people == {"mathis": 2, "mathilde": 1}, "people counted among conversations, whoever they are"
        assert facets["channels"] == [{"key": "telegram", "label": "telegram", "count": 2}]
        assert {"key": "conversation", "count": 2} in facets["kinds"]
        assert {"key": "mathilde", "label": "Mathilde", "count": 1} in facets["people"]
        assert {f["key"]: f["count"] for f in facets["rooms"]} == {}
        histogram = facets["histogram"]
        assert sum(histogram["counts"]) == 2 and histogram["bucket_s"] == 60 and histogram["from"] <= histogram["to"]
        ranged = (
            await api.get(
                "/api/v1/journal/facets",
                kinds="presence",
                **{"from": (utc_now() - timedelta(days=2)).isoformat(), "to": utc_now().isoformat()},
            )
        ).json()
        assert ranged["histogram"]["bucket_s"] == 3600 and sum(ranged["histogram"]["counts"]) == 1
        assert {f["key"]: f["count"] for f in ranged["rooms"]} == {"salon": 1}


async def test_one_entry_comes_with_its_record_and_only_to_who_may_read_it(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        await admin.nestor.journal.publish(
            UserTurn(
                medium=Medium.WRITTEN,
                exchange=Exchange(conversation_id="c1", turn_id=new_id()),
                source="agent",
                address=TELEGRAM,
                text="secret",
                speaker=Speaker.account(MATHIS),
            )
        )
        api = await admin.api()
        (item,) = await items(api, q="secret")
        entry = (await api.get(f"/api/v1/journal/{item['position']}")).json()
        assert entry["item"] == item and entry["record"]["payload"]["text"] == "secret"
        member = await admin.api("mathilde")
        assert (await member.get(f"/api/v1/journal/{item['position']}")).json()["error"][
            "code"
        ] == "journal_entry_unknown"
        assert (await api.get("/api/v1/journal/999999")).status_code == 404


async def test_signing_in_only_works_from_the_admins_own_pages(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        body = {"login": OWNER, "password": PASSWORD}
        for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {"Referer": "https://evil.example/x"}):
            api.client.headers.pop("Origin", None)
            response = await api.client.post("/api/v1/session", json=body, headers=headers)
            assert response.status_code == 403 and response.json()["error"]["code"] == "cross_origin", headers
        missing = await api.client.post("/api/v1/session", json=body)
        assert missing.status_code == 403, "a request naming no origin is refused"
        referer = await api.client.post("/api/v1/session", json=body, headers={"Referer": "http://admin.test/login"})
        assert referer.status_code == 200
        inspect = await api.client.post(
            "/api/v1/invitations/inspect", json={"token": "x"}, headers={"Origin": "https://evil.example"}
        )
        assert inspect.json()["error"]["code"] == "cross_origin"


async def test_a_conversation_threads_its_turns_and_the_journal_keeps_one(tmp_path: Path) -> None:
    now = utc_now()
    async with Harness(tmp_path, replies=("Il est midi.", "Dans le salon.", "Bonsoir.")) as admin:
        agent = admin.nestor.agent
        agent.conversations = Conversations(admin.nestor.journal, ends_after_s=lambda a, m: 300, clock=lambda: now)
        said = InboundMessage(address=TELEGRAM, sender=Sender("user"), text="Quelle heure est-il ?")
        await agent.respond(said).collect()
        await agent.respond(replace(said, text="Où ça ?")).collect()
        now += timedelta(minutes=6)
        await agent.respond(replace(said, text="Bonsoir")).collect()
        api = await admin.api()

        everything = by_type(await items(api, session=TELEGRAM.session))
        asked, follow_up, later = everything["conversation.turn.user"]
        replies = everything["conversation.turn.assistant"]
        first = asked["links"]["conversation"]
        assert first and follow_up["links"]["conversation"] == first != later["links"]["conversation"]
        assert [r["links"]["turn"] for r in replies] == [t["links"]["turn"] for t in (asked, follow_up, later)]
        assert all(r["cause"] == t["position"] for r, t in zip(replies, (asked, follow_up, later), strict=True))

        kept = await items(api, conversation=first)
        assert {i["position"] for i in kept} == {asked["position"], follow_up["position"]} | {
            r["position"] for r in replies[:2]
        }
