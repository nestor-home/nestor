"""The admin's chat: a person writes to the assistant from the admin and reads the answer as it is written, in chats of
their own, with the tools called on the way and the files they sent."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from nestor.modules.accounts import Role
from nestor.modules.cognition.model import ToolCall

from ....harness import Api, Harness

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines()]


def written(stream: list[dict[str, Any]]) -> str:
    return "".join(part.get("text", "") for part in stream if part["type"] == "text")


async def say(api: Api, chat: str, text: str = "", **body: Any) -> list[dict[str, Any]]:
    response = await api.post(f"/api/v1/chats/{chat}/messages", {"text": text, **body})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return lines(response.text)


async def test_an_answer_streams_then_stays_in_the_chat_with_the_tools_it_called(tmp_path: Path) -> None:
    replies = (ToolCall("c1", "lights", {"room": "salon"}), "C'est allumé.")
    async with Harness(tmp_path, chat=True, replies=replies) as admin:
        api = await admin.api()
        stream = await say(api, "c1", "Allume le salon")
        thread = (await api.get("/api/v1/chats/c1")).json()
        listed = (await api.get("/api/v1/chats")).json()["chats"]

    assert [p["type"] for p in stream][-1] == "done"
    assert [p for p in stream if p["type"] == "end"] == [{"type": "end", "last": True}]
    assert written(stream) == "C'est allumé."
    roles = [(m["role"], m["text"]) for m in thread["messages"]]
    assert roles == [
        ("person", "Allume le salon"),
        ("tool", ""),
        ("assistant", "C'est allumé."),
    ]
    tool = thread["messages"][1]["tool"]
    assert (tool["name"], tool["state"], tool["arguments"], tool["output"]) == (
        "lights",
        "done",
        {"room": "salon"},
        "unlocked",
    )
    assert len({m["turn"] for m in thread["messages"]}) == 1, "one turn: the message and all it caused"
    assert [(c["id"], c["title"], c["answering"]) for c in listed] == [("c1", "Allume le salon", False)]


async def test_each_chat_is_its_own_conversation_and_the_latest_comes_first(tmp_path: Path) -> None:
    async with Harness(tmp_path, chat=True, replies=("Un.", "Deux.", "Trois.")) as admin:
        api = await admin.api()
        await say(api, "a", "Premier")
        await say(api, "b", "Second")
        await say(api, "a", "Encore")
        listed = (await api.get("/api/v1/chats")).json()["chats"]
        a, b = [(await api.get(f"/api/v1/chats/{c}")).json()["messages"] for c in ("a", "b")]

    assert [(c["id"], c["title"]) for c in listed] == [("a", "Premier"), ("b", "Second")]
    assert [m["text"] for m in a] == ["Premier", "Un.", "Encore", "Trois."]
    assert [m["text"] for m in b] == ["Second", "Deux."]


async def test_a_person_reads_and_writes_only_their_own_chats(tmp_path: Path) -> None:
    async with Harness(tmp_path, chat=True, replies=("Pour Mathis.",)) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        await admin.account("robot", Role.ADMIN)
        await say(await admin.api(), "c1", "Secret")
        mathilde = await admin.api("mathilde")
        hers = (await mathilde.get("/api/v1/chats/c1")).json()
        listed = (await mathilde.get("/api/v1/chats")).json()
        nobody = await (await admin.api("robot")).get("/api/v1/chats")

    assert hers["messages"] == [] and listed["chats"] == [], "the same chat id is another chat for her"
    assert (nobody.status_code, nobody.json()["error"]["code"]) == (403, "chat_needs_person")


async def test_without_a_web_channel_the_chat_is_off(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        response = await (await admin.api()).get("/api/v1/chats")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "chat_off")


async def test_stopping_keeps_what_was_written_and_frees_the_chat(tmp_path: Path) -> None:
    long = " ".join(f"mot{i}" for i in range(200))
    async with Harness(tmp_path, chat=True, replies=(long, "Libre."), word_delay_s=0.01) as admin:
        api = await admin.api()
        answering = asyncio.create_task(say(api, "c1", "Raconte"))
        while not (await api.get("/api/v1/chats")).json()["chats"]:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        busy = await api.post("/api/v1/chats/c1/messages", {"text": "Et alors ?"})
        assert (await api.post("/api/v1/chats/c1/stop")).status_code == 204
        stream = await answering
        stopped = (await api.get("/api/v1/chats/c1")).json()["messages"][-1]
        again = await say(api, "c1", "Et alors ?")

    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "chat_busy")
    assert stream[-1] == {"type": "done"}
    assert 0 < len(written(stream).split()) < 200
    assert (stopped["role"], stopped["interrupted"], stopped["text"]) == ("assistant", True, written(stream))
    assert written(again) == "Libre."


async def test_a_page_that_comes_back_follows_the_answer_from_its_start(tmp_path: Path) -> None:
    async with Harness(tmp_path, chat=True, replies=("Un deux trois quatre",), word_delay_s=0.02) as admin:
        api = await admin.api()
        first = asyncio.create_task(say(api, "c1", "Compte"))
        while not (await api.get("/api/v1/chats/c1")).json()["answering"]:
            await asyncio.sleep(0.01)
        followed = await api.get("/api/v1/chats/c1/answer")
        await first
        after = await api.get("/api/v1/chats/c1/answer")

    assert written(lines(followed.text)) == "Un deux trois quatre"
    assert after.status_code == 204, "nothing is being written any more"


async def test_a_photo_is_kept_with_the_message_and_served_from_the_journal(tmp_path: Path) -> None:
    photo = {"kind": "image", "media_type": "image/png", "name": "salon.png", "data": base64.b64encode(PNG).decode()}
    async with Harness(tmp_path, chat=True, replies=("Joli salon.",)) as admin:
        api = await admin.api()
        await say(api, "c1", files=[photo])
        (sent, _) = (await api.get("/api/v1/chats/c1")).json()["messages"]
        (file,) = sent["files"]
        served = await api.get(f"/api/v1/journal/{file['position']}/attachments/{file['index']}")
        title = (await api.get("/api/v1/chats")).json()["chats"][0]

    assert (sent["text"], file["kind"], file["name"], file["size"]) == ("", "image", "salon.png", len(PNG))
    assert served.content == PNG
    assert (title["title"], title["files"]) == ("", ["image"]), "a chat opened with a photo is named by it"


async def test_a_message_says_something_in_a_file_the_server_can_read(tmp_path: Path) -> None:
    async with Harness(tmp_path, chat=True) as admin:
        api = await admin.api()
        empty = await api.post("/api/v1/chats/c1/messages", {"text": "  "})
        garbled = await api.post(
            "/api/v1/chats/c1/messages",
            {"files": [{"kind": "file", "media_type": "text/plain", "data": "not base64!"}]},
        )
        bad_id = await api.get("/api/v1/chats/a%2Fb")
    assert empty.status_code == garbled.status_code == 422
    assert bad_id.status_code in (404, 422)


async def test_a_message_can_name_the_executors_plugged_in(tmp_path: Path) -> None:
    async with Harness(tmp_path, chat=True) as admin:
        mentions = (await (await admin.api()).get("/api/v1/chats/mentions")).json()
        plugged = list(admin.nestor.tasks.executors)
    assert [m["name"] for m in mentions] == plugged and plugged, "the names the model delegates to"


async def test_nobody_else_reads_a_chat_through_the_journal_or_its_files(tmp_path: Path) -> None:
    photo = {"kind": "image", "media_type": "image/png", "data": base64.b64encode(PNG).decode()}
    async with Harness(tmp_path, chat=True, replies=("Vu.",)) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        mathis = await admin.api()
        await say(mathis, "c1", "Mon secret", files=[photo])
        (sent, _) = (await mathis.get("/api/v1/chats/c1")).json()["messages"]
        session = (await mathis.get("/api/v1/chats/c1")).json()["session"]
        mathilde = await admin.api("mathilde")
        journal = (await mathilde.get("/api/v1/journal", session=session)).json()["items"]
        file = await mathilde.get(f"/api/v1/journal/{sent['position']}/attachments/0")
        stop = await mathilde.post("/api/v1/chats/c1/stop")
        anonymous = await (await admin.api(None)).get("/api/v1/chats")
    assert journal == [] and file.status_code == 404
    assert stop.status_code == 204, "her own chat c1, which answers nothing"
    assert anonymous.status_code == 401
