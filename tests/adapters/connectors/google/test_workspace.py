"""Calendar, Drive, Contacts and Tasks of a connected Google account, against a fake of Google's APIs."""

import urllib.parse
from datetime import datetime
from typing import Any

import httpx
import pytest

from nestor.adapters.connectors.google.connector import GoogleConnector
from nestor.core import PersonId
from nestor.modules.cognition.tools import ToolFailed
from nestor.modules.connectors import Connection

from ..accounts import CONTEXT, TOKEN, FakeAccess
from .fakes import error

CONNECTION = Connection(kind="google", owner=PersonId("mathis"), account="mathis@gmail.com", id="google-math")
DOC = "application/vnd.google-apps.document"


class FakeGoogle:
    """Plays Calendar, Drive, People and Tasks for one account; `refusing` answers every call with its error."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.files: dict[str, dict[str, Any]] = {}  # by id: metadata, and `content` by exported or own type
        self.contacts: list[dict[str, Any]] = []
        self.tasks: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.refusing: httpx.Response | None = None
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return error(401, "authError", "Request had invalid authentication credentials.")
        if self.refusing is not None:
            return self.refusing
        url, query = request.url, dict(urllib.parse.parse_qsl(request.url.query.decode(), keep_blank_values=True))
        if url.path == "/calendar/v3/calendars/primary/events":
            return self.calendar(request, query)
        if url.path.startswith("/drive/v3/files"):
            return self.drive(url.path.removeprefix("/drive/v3/files").strip("/"), query)
        if url.path == "/v1/people:searchContacts":
            words = query["query"].lower()
            found = [c for c in self.contacts if words and words in str(c).lower()][: int(query.get("pageSize", 10))]
            return httpx.Response(200, json={"results": [{"person": c} for c in found]} if found else {})
        if url.path.startswith("/tasks/v1/lists/@default/tasks"):
            return self.task(request, url.path.removeprefix("/tasks/v1/lists/@default/tasks").strip("/"), query)
        return error(404, "notFound", "Not Found")

    def calendar(self, request: httpx.Request, query: dict[str, str]) -> httpx.Response:
        if request.method == "POST":
            event = {"id": f"ev{len(self.events)}", **httpx.Response(200, content=request.content).json()}
            self.events.append(event)
            return httpx.Response(200, json=event)
        since, until = datetime.fromisoformat(query["timeMin"]), datetime.fromisoformat(query["timeMax"])
        words = query.get("q", "").lower()
        found = sorted(
            (e for e in self.events if since <= _start(e) < until and words in e["summary"].lower()), key=_start
        )
        return httpx.Response(200, json={"items": found[: int(query["maxResults"])]})

    def drive(self, path: str, query: dict[str, str]) -> httpx.Response:
        if not path:
            words = query["q"].removeprefix("fullText contains '").partition("' and trashed")[0].replace("\\'", "'")
            found = [{k: v for k, v in f.items() if k != "content"} for f in self.files.values() if words in f["name"]]
            return httpx.Response(200, json={"files": found})
        file_id, _, action = path.partition("/")
        file = self.files.get(file_id)
        if file is None:
            return error(404, "notFound", f"File not found: {file_id}.")
        if action == "export" or query.get("alt") == "media":
            wanted = query.get("mimeType", file["mimeType"])
            if wanted not in file["content"]:
                return error(400, "badRequest", "Export only supports Docs Editors files.")
            return httpx.Response(200, content=file["content"][wanted], headers={"content-type": wanted})
        return httpx.Response(200, json={k: v for k, v in file.items() if k != "content"})

    def task(self, request: httpx.Request, task_id: str, query: dict[str, str]) -> httpx.Response:
        if request.method == "GET":
            open_ = [t for t in self.tasks if query.get("showCompleted") != "false" or t["status"] != "completed"]
            return httpx.Response(200, json={"items": open_})
        body = httpx.Response(200, content=request.content).json()
        if request.method == "POST":
            self.tasks.append({"id": f"t{len(self.tasks)}", "status": "needsAction", **body})
            return httpx.Response(200, json=self.tasks[-1])
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if task is None:
            return error(404, "notFound", "Task not found.")
        task.update(body)
        return httpx.Response(200, json=task)

    def sent(self, method: str) -> list[dict[str, Any]]:
        return [httpx.Response(200, content=r.content).json() for r in self.requests if r.method == method]


def _start(event: dict[str, Any]) -> datetime:
    start = event["start"]
    return datetime.fromisoformat(start.get("dateTime") or f"{start['date']}T00:00:00+00:00")


def tools(google: FakeGoogle, **options: Any) -> dict[str, Any]:
    connector = GoogleConnector(transport=google.transport, **options)
    return {t.name: t for t in connector.tools(CONNECTION, FakeAccess())}


async def run(google: FakeGoogle, name: str, **arguments: Any) -> Any:
    return await tools(google)[name].run(arguments, CONTEXT)


# -- Calendar ------------------------------------------------------------------------------------------


def timed(summary: str, start: str, end: str, **more: Any) -> dict[str, Any]:
    return {"id": summary, "summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}, **more}


async def test_events_between_two_instants_come_in_order_with_what_the_model_needs() -> None:
    google = FakeGoogle()
    google.events = [
        timed("Dentiste", "2026-11-14T15:00:00+01:00", "2026-11-14T15:30:00+01:00", location="12 rue Victor Hugo"),
        timed("Piscine", "2026-11-14T09:00:00+01:00", "2026-11-14T10:00:00+01:00", attendees=[{"email": "lea@x.fr"}]),
        timed("Réunion", "2026-11-15T09:00:00+01:00", "2026-11-15T10:00:00+01:00"),
    ]
    found = await run(
        google, "google_calendar_events", since="2026-11-14T00:00:00+01:00", until="2026-11-15T00:00+01:00"
    )
    assert [e["title"] for e in found["events"]] == ["Piscine", "Dentiste"]
    assert found["events"][0]["attendees"] == ["lea@x.fr"] and found["events"][1]["location"] == "12 rue Victor Hugo"
    assert found["account"] == "mathis@gmail.com"
    only = await run(
        google, "google_calendar_events", since="2026-11-01T00:00:00Z", until="2026-12-01T00:00:00Z", query="réu"
    )
    assert [e["title"] for e in only["events"]] == ["Réunion"]


@pytest.mark.parametrize("since", ["2026-11-14", "2026-11-14T09:00:00", "demain"])
async def test_a_search_bound_needs_an_instant_with_its_offset(since: str) -> None:
    google = FakeGoogle()
    with pytest.raises(ToolFailed, match="offset"):
        await run(google, "google_calendar_events", since=since, until="2026-11-15T00:00:00+01:00")
    assert not google.requests


async def test_a_timed_or_whole_day_event_is_added_as_google_takes_it() -> None:
    google = FakeGoogle()
    made = await run(
        google,
        "google_calendar_create",
        title="Dîner chez Mamie",
        start="2026-11-20T19:30:00+01:00",
        end="2026-11-20T22:00:00+01:00",
        location="Lyon",
    )
    holiday = await run(google, "google_calendar_create", title="Vacances", start="2026-12-21", end="2027-01-04")
    first, second = google.sent("POST")
    assert first["start"] == {"dateTime": "2026-11-20T19:30:00+01:00"} and first["location"] == "Lyon"
    assert second["start"] == {"date": "2026-12-21"} and second["end"] == {"date": "2027-01-04"}
    assert made["event"]["title"] == "Dîner chez Mamie" and holiday["event"]["all_day"]


@pytest.mark.parametrize(
    ("start", "end", "reason"),
    [
        ("2026-11-20", "2026-11-20T22:00:00+01:00", "both dates"),
        ("2026-11-20T22:00:00+01:00", "2026-11-20T19:00:00+01:00", "after the start"),
        ("2026-11-20T19:00:00", "2026-11-20T22:00:00", "offset"),
    ],
)
async def test_an_event_that_cannot_be_placed_is_refused_before_anything_is_sent(
    start: str, end: str, reason: str
) -> None:
    google = FakeGoogle()
    with pytest.raises(ToolFailed, match=reason):
        await run(google, "google_calendar_create", title="Dîner", start=start, end=end)
    assert not google.requests


# -- Drive ---------------------------------------------------------------------------------------------


def file(
    file_id: str, name: str, media_type: str, content: dict[str, bytes], size: int | None = None
) -> dict[str, Any]:
    meta: dict[str, Any] = {"id": file_id, "name": name, "mimeType": media_type, "content": content}
    if size is not None:
        meta["size"] = str(size)
    return meta


async def test_a_drive_search_quotes_the_words_and_leaves_the_trash_out() -> None:
    google = FakeGoogle()
    google.files["d1"] = file("d1", "Contrat d'assurance", DOC, {"text/plain": b"x"})
    found = await run(google, "google_drive_search", query="d'assurance")
    assert [f["name"] for f in found["files"]] == ["Contrat d'assurance"]
    q = dict(urllib.parse.parse_qsl(google.requests[0].url.query.decode()))["q"]
    assert q == "fullText contains 'd\\'assurance' and trashed = false"


async def test_google_documents_are_read_as_the_text_they_export_to() -> None:
    google = FakeGoogle()
    google.files["d1"] = file("d1", "Notes", DOC, {"text/plain": "Franchise : 150 €".encode()})
    google.files["s1"] = file("s1", "Budget", "application/vnd.google-apps.spreadsheet", {"text/csv": b"loyer,900"})
    assert (await run(google, "google_drive_read", id="d1"))["text"] == "Franchise : 150 €"
    assert (await run(google, "google_drive_read", id="s1"))["text"] == "loyer,900"


async def test_a_file_or_an_export_is_read_only_within_the_size_limit() -> None:
    google = FakeGoogle()
    google.files["t1"] = file("t1", "liste.txt", "text/plain", {"text/plain": b"lait, oeufs"})
    google.files["big"] = file("big", "scan.txt", "text/plain", {"text/plain": b"x" * 1_000_001})
    google.files["doc"] = file("doc", "Thèse", DOC, {"text/plain": b"x" * 1_000_001})  # Google gives no size
    found = tools(google, file_bytes=1_000_000)
    assert (await found["google_drive_read"].run({"id": "t1"}, CONTEXT))["text"] == "lait, oeufs"
    for file_id in ("big", "doc"):
        with pytest.raises(ToolFailed, match="larger than 1 MB"):
            await found["google_drive_read"].run({"id": file_id}, CONTEXT)


async def test_a_folder_or_an_image_is_not_a_document_to_read() -> None:
    google = FakeGoogle()
    google.files["f1"] = file("f1", "Factures", "application/vnd.google-apps.folder", {})
    google.files["p1"] = file("p1", "photo.jpg", "image/jpeg", {"image/jpeg": b"\xff\xd8"}, size=2)
    for file_id in ("f1", "p1"):
        with pytest.raises(ToolFailed, match="not a document to read"):
            await run(google, "google_drive_read", id=file_id)


async def test_reading_an_unknown_file_tells_the_model_to_check_the_id() -> None:
    with pytest.raises(ToolFailed, match="not found"):
        await run(FakeGoogle(), "google_drive_read", id="nope")


# -- Contacts ------------------------------------------------------------------------------------------


async def test_a_contact_is_found_after_refreshing_google_s_cache() -> None:
    google = FakeGoogle()
    google.contacts = [
        {
            "names": [{"displayName": "Mamie Jeanne"}],
            "phoneNumbers": [{"value": "+33 6 12 34 56 78"}],
            "emailAddresses": [{"value": "jeanne@x.fr"}],
            "addresses": [{"formattedValue": "3 place Bellecour, Lyon"}],
            "birthdays": [{"date": {"month": 3, "day": 9}}],
        }
    ]
    found = await run(google, "google_contacts_search", query="Jeanne")
    assert found["contacts"] == [
        {
            "name": "Mamie Jeanne",
            "emails": ["jeanne@x.fr"],
            "phones": ["+33 6 12 34 56 78"],
            "addresses": ["3 place Bellecour, Lyon"],
            "birthday": "03-09",
            "company": "",
        }
    ]
    assert [r.url.params["query"] for r in google.requests] == ["", "Jeanne"]


# -- Tasks ---------------------------------------------------------------------------------------------


async def test_tasks_are_listed_open_added_with_their_day_and_ticked_off() -> None:
    google = FakeGoogle()
    added = await run(google, "google_tasks_add", title="Appeler le plombier", due="2026-11-16", notes="fuite")
    assert google.sent("POST")[0]["due"] == "2026-11-16T00:00:00.000Z"
    assert added["task"]["due"] == "2026-11-16" and not added["task"]["done"]
    await run(google, "google_tasks_add", title="Racheter du café")
    await run(google, "google_tasks_complete", id=added["task"]["id"])
    listed = await run(google, "google_tasks_list")
    assert [t["title"] for t in listed["tasks"]] == ["Racheter du café"]


async def test_a_task_with_an_unreadable_day_or_an_unknown_id_is_refused() -> None:
    google = FakeGoogle()
    with pytest.raises(ToolFailed, match="YYYY-MM-DD"):
        await run(google, "google_tasks_add", title="x", due="lundi")
    with pytest.raises(ToolFailed, match="not found"):
        await run(google, "google_tasks_complete", id="nope")


# -- failures ------------------------------------------------------------------------------------------


async def test_an_api_the_household_did_not_enable_is_a_failure_that_says_so() -> None:
    google = FakeGoogle()
    google.refusing = httpx.Response(
        403,
        json={"error": {"code": 403, "message": "Tasks API has not been used in project 42 before or it is disabled.",
                        "errors": [{"reason": "accessNotConfigured"}]}},
    )  # fmt: skip
    with pytest.raises(ToolFailed, match=r"accessNotConfigured.*disabled"):
        await run(google, "google_tasks_list")
