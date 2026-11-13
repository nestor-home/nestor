"""The Microsoft 365 connector against a fake of Microsoft Graph: Outlook mail and its feed for watches, the
calendar, OneDrive and To Do."""

import asyncio
import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from nestor.adapters.connectors.common import Every
from nestor.adapters.connectors.microsoft.connector import INFO, MicrosoftConnector
from nestor.adapters.connectors.microsoft.inbound import OutlookInbound
from nestor.core import ProviderError
from nestor.modules.cognition.tools import Risk, ToolFailed
from nestor.modules.connectors import Connection
from nestor.modules.initiative import Incoming
from nestor.testing.documents import text_pdf
from nestor.testing.initiative import InboundEventSourceContract

from ..accounts import CONTEXT, MATHIS, TOKEN, FakeAccess

CONNECTION = Connection(kind="microsoft", owner=MATHIS, account="mathis@outlook.fr", id="ms-math")
ZONE = "Romance Standard Time"


def error(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message}})


class FakeGraph:
    """Plays Microsoft Graph for one account. Times of events are kept as Graph does: a local time and its zone."""

    def __init__(self) -> None:
        self.inbox: list[dict[str, Any]] = []
        self.delivered = 0  # messages ever delivered: each has its own id, archived or not
        self.events: list[dict[str, Any]] = []
        self.files: dict[str, dict[str, Any]] = {}  # by id: the item, and `content` by format ("" for its own)
        self.tasks: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.refusing: httpx.Response | None = None
        self.page = 2
        self.transport = httpx.MockTransport(self.handle)

    def deliver(self, subject: str, *, at: datetime | None = None, sender: str = "noreply@colissimo.fr") -> str:
        self.delivered += 1
        message_id = f"AAMk{self.delivered:04d}"
        received = (at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.inbox.append(
            {
                "id": message_id,
                "conversationId": f"c{message_id}",
                "subject": subject,
                "receivedDateTime": received,
                "from": {"emailAddress": {"name": "Colissimo", "address": sender}},
                "toRecipients": [{"emailAddress": {"name": "Mathis", "address": "mathis@outlook.fr"}}],
                "body": {"contentType": "text", "content": f"{subject}, le détail."},
                "bodyPreview": f"{subject}, le détail.",
                "hasAttachments": False,
            }
        )
        return message_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return error(401, "InvalidAuthenticationToken", "Access token is empty.")
        if self.refusing is not None:
            return self.refusing
        path = urllib.parse.unquote(request.url.path).removeprefix("/v1.0")
        query = {k: v for k, v in request.url.params.items()}
        body = json.loads(request.content) if request.content else {}
        match path.split("/")[1:]:
            case ["me"]:
                return httpx.Response(200, json={"mail": "mathis@outlook.fr", "userPrincipalName": "mathis@outlook.fr"})
            case ["me", "mailFolders", "inbox", "messages"]:
                return self.received(query)
            case ["me", "messages"]:
                words = query["$search"].strip('"').lower()
                return httpx.Response(200, json={"value": [m for m in self.inbox if words in m["subject"].lower()]})
            case ["me", "messages", message_id]:
                found = next((m for m in self.inbox if m["id"] == message_id), None)
                return httpx.Response(200, json=found) if found else error(404, "ErrorItemNotFound", "Not found.")
            case ["me", "mailboxSettings", "timeZone"]:
                return httpx.Response(200, json={"value": ZONE})
            case ["me", "calendarView"]:
                since, until = query["startDateTime"], query["endDateTime"]
                found = [e for e in self.events if since[:10] <= e["start"]["dateTime"][:10] < until[:10]]
                found = sorted(found, key=lambda e: e["start"]["dateTime"])[: int(query.get("$top", "10"))]
                return httpx.Response(200, json={"value": found})
            case ["me", "events"]:
                self.events.append({"id": f"ev{len(self.events)}", **body})
                return httpx.Response(201, json=self.events[-1])
            case ["me", "drive", "root", found] if found.startswith("search(q='"):
                quoted = found.removeprefix("search(q='").removesuffix("')")
                if "'" in quoted.replace("''", ""):
                    return error(400, "BadRequest", "Syntax error: character '\\'' is not valid.")
                words = quoted.replace("''", "'")
                listed = [{k: v for k, v in f.items() if k != "content"} for f in self.files.values()]
                return httpx.Response(200, json={"value": [f for f in listed if words in f["name"]]})
            case ["me", "drive", "items", file_id, *rest]:
                return self.item(file_id, rest, query)
            case ["me", "todo", "lists"]:
                lists = [{"id": "L1", "displayName": "Courses"}, {"id": "L0", "wellknownListName": "defaultList"}]
                return httpx.Response(200, json={"value": lists})
            case ["me", "todo", "lists", "L0", "tasks", *task]:
                return self.task(request.method, task, query, body)
        return error(404, "ResourceNotFound", f"no route {path}")

    def received(self, query: dict[str, str]) -> httpx.Response:
        since = query["$filter"].removeprefix("receivedDateTime ge ")
        found = sorted((m for m in self.inbox if m["receivedDateTime"] >= since), key=lambda m: m["receivedDateTime"])
        skip = int(query.get("$skip", "0"))
        page: dict[str, Any] = {"value": found[skip : skip + self.page]}
        if skip + self.page < len(found):
            params = urllib.parse.urlencode({**query, "$skip": skip + self.page})
            page["@odata.nextLink"] = f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?{params}"
        return httpx.Response(200, json=page)

    def item(self, file_id: str, rest: list[str], query: dict[str, str]) -> httpx.Response:
        file = self.files.get(file_id)
        if file is None:
            return error(404, "itemNotFound", "The resource could not be found.")
        if rest == ["content"]:
            content = file["content"].get(query.get("format", ""))
            return httpx.Response(200, content=content) if content else error(406, "notSupported", "Cannot convert.")
        return httpx.Response(200, json={k: v for k, v in file.items() if k != "content"})

    def task(self, method: str, task: list[str], query: dict[str, str], body: dict[str, Any]) -> httpx.Response:
        if method == "GET":
            return httpx.Response(200, json={"value": [t for t in self.tasks if t["status"] != "completed"]})
        if method == "POST":
            self.tasks.append({"id": f"t{len(self.tasks)}", "status": "notStarted", **body})
            return httpx.Response(201, json=self.tasks[-1])
        found = next((t for t in self.tasks if [t["id"]] == task), None)
        if found is None:
            return error(404, "ErrorItemNotFound", "The specified object was not found in the store.")
        found.update(body)
        return httpx.Response(200, json=found)


def tools(graph: FakeGraph, **options: Any) -> dict[str, Any]:
    connector = MicrosoftConnector(transport=graph.transport, **options)
    return {t.name: t for t in connector.tools(CONNECTION, FakeAccess())}


async def run(graph: FakeGraph, name: str, **arguments: Any) -> Any:
    return await tools(graph)[name].run(arguments, CONTEXT)


def test_the_connector_asks_for_a_refresh_token_and_writes_only_events_and_tasks() -> None:
    assert INFO.oauth is not None and "offline_access" in INFO.oauth.scopes
    assert not any(s.startswith(("Mail.Send", "Mail.ReadWrite", "Files.ReadWrite")) for s in INFO.oauth.scopes)
    found = tools(FakeGraph())
    writing = {name for name, tool in found.items() if tool.risk is not Risk.READ}
    assert writing == {"outlook_calendar_create", "todo_add", "todo_complete"}
    assert sorted(n for s in INFO.services for n in s.tools) == sorted(found)


async def test_connecting_names_the_account_by_its_address() -> None:
    async with MicrosoftConnector(transport=FakeGraph().transport) as connector:
        assert await connector.identify(FakeAccess()) == "mathis@outlook.fr"


# -- Outlook mail --------------------------------------------------------------------------------------


async def test_mail_is_searched_and_read_with_its_sender_and_recipients() -> None:
    graph = FakeGraph()
    message_id = graph.deliver("Votre colis arrive")
    graph.deliver("Facture EDF")
    found = await run(graph, "outlook_mail_search", query='"colis"')
    assert [(m["id"], m["from"]) for m in found["messages"]] == [(message_id, "Colissimo <noreply@colissimo.fr>")]
    assert graph.requests[-1].url.params["$search"] == '"colis"'  # the person's quotes cannot break Graph's
    read = await run(graph, "outlook_mail_read", id=message_id)
    assert (read["to"], read["body"]) == ("Mathis <mathis@outlook.fr>", "Votre colis arrive, le détail.")
    assert 'outlook.body-content-type="text"' in graph.requests[-1].headers["prefer"]


# -- the feed for watches ------------------------------------------------------------------------------


def inbound(graph: FakeGraph, access: FakeAccess) -> OutlookInbound:
    return OutlookInbound(CONNECTION, access, wakeup=Every(0.01), blocked_s=0.01, transport=graph.transport)


async def take(source: OutlookInbound, count: int) -> list[Incoming]:
    feed = source.items()
    try:
        return [await asyncio.wait_for(anext(feed), 5.0) for _ in range(count)]
    finally:
        await feed.aclose()


class TestOutlookInbound(InboundEventSourceContract):
    @pytest.fixture(autouse=True)
    def _mailbox(self) -> None:
        self.graph, self.access = FakeGraph(), FakeAccess()

    def source(self) -> OutlookInbound:
        return inbound(self.graph, self.access)

    async def arrive(self, title: str) -> None:
        self.graph.deliver(title)


async def test_mail_from_before_the_first_start_is_not_yielded() -> None:
    graph, access = FakeGraph(), FakeAccess()
    graph.deliver("Ancienne facture", at=datetime.now(UTC) - timedelta(hours=1))
    async with inbound(graph, access) as source:
        graph.deliver("Votre colis est en route")
        [item] = await take(source, 1)
    assert (item.title, item.sender, item.owner) == (
        "Votre colis est en route",
        "Colissimo <noreply@colissimo.fr>",
        MATHIS,
    )


async def test_many_messages_received_in_the_same_second_come_once_across_pages() -> None:
    graph, access = FakeGraph(), FakeAccess()
    async with inbound(graph, access) as source:
        moment = datetime.now(UTC) + timedelta(seconds=5)
        for title in ("un", "deux", "trois", "quatre", "cinq"):
            graph.deliver(title, at=moment)
        assert [i.title for i in await take(source, 5)] == ["un", "deux", "trois", "quatre", "cinq"]
        graph.deliver("six", at=moment)
        assert [i.title for i in await take(source, 1)] == ["six"]


async def test_a_message_archived_meanwhile_never_hides_the_next_one() -> None:
    graph, access = FakeGraph(), FakeAccess()
    async with inbound(graph, access) as source:
        moment = datetime.now(UTC) + timedelta(seconds=5)
        graph.deliver("Lu puis archivé", at=moment)
        await take(source, 1)
        graph.inbox.clear()
        graph.deliver("Le suivant", at=moment + timedelta(seconds=1))
        [item] = await take(source, 1)
    assert item.title == "Le suivant"


async def test_a_revoked_authorisation_pauses_the_feed_until_the_person_reconnects() -> None:
    graph, access = FakeGraph(), FakeAccess()
    async with inbound(graph, access) as source:
        access.refusals = 3
        graph.deliver("Après la reconnexion")
        [item] = await take(source, 1)
    assert item.title == "Après la reconnexion" and access.refusals == 0


# -- calendar ------------------------------------------------------------------------------------------


async def test_events_are_shown_in_the_mailbox_time_zone_and_filtered_by_words() -> None:
    graph = FakeGraph()
    graph.events = [
        {"id": "a", "subject": "Dentiste", "isAllDay": False, "location": {"displayName": "Cabinet"},
         "start": {"dateTime": "2026-11-14T15:00:00.0000000", "timeZone": ZONE},
         "end": {"dateTime": "2026-11-14T15:30:00.0000000", "timeZone": ZONE}},
        {"id": "b", "subject": "Férié", "isAllDay": True,
         "start": {"dateTime": "2026-11-11T00:00:00.0000000", "timeZone": ZONE},
         "end": {"dateTime": "2026-11-12T00:00:00.0000000", "timeZone": ZONE}},
    ]  # fmt: skip
    found = await run(
        graph, "outlook_calendar_events", since="2026-11-10T00:00:00+01:00", until="2026-11-20T00:00:00+01:00"
    )
    assert [(e["title"], e["start"], e["all_day"]) for e in found["events"]] == [
        ("Férié", "2026-11-11", True),
        ("Dentiste", "2026-11-14T15:00:00", False),
    ]
    assert found["time_zone"] == ZONE and graph.requests[-1].headers["prefer"] == f'outlook.timezone="{ZONE}"'
    only = await run(
        graph, "outlook_calendar_events", since="2026-11-10T00:00:00Z", until="2026-11-20T00:00:00Z", query="cabinet"
    )
    assert [e["title"] for e in only["events"]] == ["Dentiste"]


async def test_a_timed_event_is_sent_in_utc_and_a_whole_day_at_midnight_where_the_person_lives() -> None:
    graph = FakeGraph()
    await run(
        graph,
        "outlook_calendar_create",
        title="Dîner",
        start="2026-11-20T19:30:00+01:00",
        end="2026-11-20T22:00:00+01:00",
    )
    await run(graph, "outlook_calendar_create", title="Vacances", start="2026-12-21", end="2027-01-04", location="Lyon")
    timed, whole = graph.events
    assert timed["start"] == {"dateTime": "2026-11-20T18:30:00", "timeZone": "UTC"} and not timed["isAllDay"]
    assert whole["start"] == {"dateTime": "2026-12-21T00:00:00", "timeZone": ZONE} and whole["isAllDay"]
    assert whole["location"] == {"displayName": "Lyon"}


async def test_an_event_that_cannot_be_placed_is_refused_before_anything_is_sent() -> None:
    graph = FakeGraph()
    with pytest.raises(ToolFailed, match="after the start"):
        await run(graph, "outlook_calendar_create", title="x", start="2026-11-20T22:00:00Z", end="2026-11-20T19:00:00Z")
    assert not graph.requests


# -- OneDrive ------------------------------------------------------------------------------------------


async def test_files_are_found_and_office_documents_read_through_their_pdf() -> None:
    graph = FakeGraph()
    word = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    graph.files["w1"] = {"id": "w1", "name": "Contrat d'assurance.docx", "size": 2048, "file": {"mimeType": word},
                         "content": {"pdf": text_pdf("Franchise 150 EUR")}}  # fmt: skip
    graph.files["t1"] = {"id": "t1", "name": "liste.txt", "size": 11, "file": {"mimeType": "text/plain"},
                         "content": {"": b"lait, oeufs"}}  # fmt: skip
    found = await run(graph, "onedrive_search", query="d'assurance")
    assert [f["name"] for f in found["files"]] == ["Contrat d'assurance.docx"]
    assert "Franchise 150 EUR" in (await run(graph, "onedrive_read", id="w1"))["text"]
    assert (await run(graph, "onedrive_read", id="t1"))["text"] == "lait, oeufs"


async def test_a_folder_or_a_picture_is_not_read_nor_downloaded() -> None:
    graph = FakeGraph()
    graph.files["f"] = {"id": "f", "name": "Factures", "folder": {"childCount": 3}, "content": {}}
    graph.files["p"] = {"id": "p", "name": "photo.jpg", "size": 9, "file": {"mimeType": "image/jpeg"}, "content": {}}
    for file_id, reason in (("f", "folder"), ("p", "not a document")):
        with pytest.raises(ToolFailed, match=reason):
            await run(graph, "onedrive_read", id=file_id)
    assert not any(r.url.path.endswith("/content") for r in graph.requests)


async def test_a_conversion_larger_than_the_limit_is_refused() -> None:
    graph = FakeGraph()
    graph.files["w"] = {"id": "w", "name": "Thèse.docx", "size": 9, "file": {"mimeType": "application/msword"},
                        "content": {"pdf": b"%PDF" + b"x" * 1_000_000}}  # fmt: skip
    with pytest.raises(ToolFailed, match="larger than 1 MB"):
        await tools(graph, file_bytes=1_000_000)["onedrive_read"].run({"id": "w"}, CONTEXT)


# -- To Do ---------------------------------------------------------------------------------------------


async def test_tasks_go_to_the_default_list_and_are_ticked_off() -> None:
    graph = FakeGraph()
    added = await run(graph, "todo_add", title="Appeler le plombier", due="2026-11-16", notes="fuite")
    assert graph.tasks[0]["dueDateTime"] == {"dateTime": "2026-11-16T00:00:00", "timeZone": ZONE}, "the person's day"
    assert added["task"]["due"] == "2026-11-16" and added["task"]["notes"] == "fuite"
    await run(graph, "todo_add", title="Racheter du café")
    await run(graph, "todo_complete", id=added["task"]["id"])
    assert [t["title"] for t in (await run(graph, "todo_list"))["tasks"]] == ["Racheter du café"]
    with pytest.raises(ToolFailed, match="not found"):
        await run(graph, "todo_complete", id="nope")


# -- failures ------------------------------------------------------------------------------------------


async def test_throttling_is_transient_and_reaches_the_model_with_graph_s_words() -> None:
    graph = FakeGraph()
    graph.refusing = error(429, "TooManyRequests", "Please retry after 10 seconds.")
    with pytest.raises(ToolFailed, match="TooManyRequests: Please retry"):
        await run(graph, "todo_list")
    async with MicrosoftConnector(transport=graph.transport) as connector:
        with pytest.raises(ProviderError) as raised:
            await connector.identify(FakeAccess())
    assert raised.value.transient


async def test_words_are_searched_through_the_whole_span_not_only_its_first_events() -> None:
    graph = FakeGraph()
    graph.events = [
        {"id": f"e{i}", "subject": "Dentiste" if i == 34 else f"Réunion {i}", "isAllDay": False,
         "start": {"dateTime": f"2026-12-{1 + i // 2:02d}T09:00:00.0000000", "timeZone": ZONE},
         "end": {"dateTime": f"2026-12-{1 + i // 2:02d}T10:00:00.0000000", "timeZone": ZONE}}
        for i in range(40)
    ]  # fmt: skip
    found = await run(
        graph,
        "outlook_calendar_events",
        since="2026-12-01T00:00:00+01:00",
        until="2027-01-01T00:00:00+01:00",
        query="dentiste",
    )
    assert [e["title"] for e in found["events"]] == ["Dentiste"]


async def test_words_and_ids_from_the_model_stay_inside_their_part_of_the_address() -> None:
    graph = FakeGraph()
    await run(graph, "onedrive_search", query="facture #12?")
    with pytest.raises(ToolFailed, match="not found"):
        await run(graph, "outlook_mail_read", id="../drive/root")
    searched, read = graph.requests[-2].url.raw_path.decode(), graph.requests[-1].url.raw_path.decode()
    assert "facture%20%2312%3F" in searched, "the words stay in the search, not a fragment or a query"
    assert "/me/messages/..%2Fdrive%2Froot" in read, "an id stays one segment of the path"
