"""The CalDAV and CardDAV connector against a fake server laid out like Nextcloud: discovery (straight or through the
well-known address), events, contacts."""

import base64
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from nestor.adapters.connectors.dav.connector import INFO, DavConnector
from nestor.core import ProviderError
from nestor.modules.cognition.tools import Risk, ToolFailed
from nestor.modules.connectors import Access, Connection, Secrets

from ..accounts import CONTEXT, MATHIS

CONNECTION = Connection(kind="dav", owner=MATHIS, account="mathis", id="dav-math")
HOST = "https://cloud.example"
DAV = f"{HOST}/remote.php/dav"
PRINCIPAL = "/remote.php/dav/principals/users/mathis/"
CALENDARS = "/remote.php/dav/calendars/mathis/"
BOOKS = "/remote.php/dav/addressbooks/users/mathis/"
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "a": "urn:ietf:params:xml:ns:carddav"}


class DavAccess(Access):
    def __init__(self, **secrets: str) -> None:
        self.values = {"server": DAV, "username": "mathis", "password": "app-pass", **secrets}

    async def token(self) -> str:
        raise AssertionError("a DAV account has no token")

    async def secrets(self) -> Secrets:
        return self.values

    async def load_state(self) -> Mapping[str, str]:
        return {}

    async def save_state(self, state: Mapping[str, str]) -> None:
        pass


def multistatus(*responses: str) -> httpx.Response:
    body = f'<d:multistatus xmlns:d="DAV:" xmlns:c="{NS["c"]}" xmlns:a="{NS["a"]}">{"".join(responses)}</d:multistatus>'
    return httpx.Response(207, content=body.encode(), headers={"content-type": "application/xml"})


def response(href: str, props: str) -> str:
    return f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{props}</d:prop></d:propstat></d:response>"


def href(prop: str, url: str) -> str:
    return f"<{prop}><d:href>{url}</d:href></{prop}>"


def item(url: str, prop: str, data: str) -> str:
    return response(url, f"<{prop}>{data}</{prop}>")


def calendar(name: str, display: str, component: str) -> str:
    props = (
        f"<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>{display}</d:displayname>"
        f'<c:supported-calendar-component-set><c:comp name="{component}"/></c:supported-calendar-component-set>'
    )
    return response(f"{CALENDARS}{name}/", props)


def _day(event: str) -> str:
    found = re.search(r"DTSTART[^:]*:(\d{8})", event)
    return found[1] if found else ""


def vevent(summary: str, start: str, end: str, **more: str) -> str:
    extra = "".join(f"{k.upper()}:{v}\r\n" for k, v in more.items())
    return (
        f"BEGIN:VEVENT\r\nUID:{summary}\r\nSUMMARY:{summary}\r\nDTSTART{start}\r\nDTEND{end}\r\n{extra}END:VEVENT\r\n"
    )


def vcard(*lines: str) -> str:
    return "\r\n".join(("BEGIN:VCARD", "VERSION:3.0", *lines, "END:VCARD")) + "\r\n"


class FakeDav:
    """A Nextcloud-like server: `/remote.php/dav` answers the principal; the host's root does not speak DAV, and its
    well-known address redirects there. Calendars hold events already expanded (in UTC), as `expand` asks."""

    def __init__(self) -> None:
        self.calendars: dict[str, list[str]] = {"perso": [], "travail": []}
        self.forbidden: set[str] = set()  # calendars that refuse to be read or written (shared, subscribed)
        self.home: str | None = None  # the calendar home on another host, as iCloud's partitions
        self.root_page = False  # the host's root answers with a web page rather than a refusal
        self.cards: list[str] = []
        self.put: dict[str, tuple[str, Mapping[str, str]]] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        expected = "Basic " + base64.b64encode(b"mathis:app-pass").decode()
        if request.headers.get("authorization") != expected:
            return httpx.Response(401, headers={"WWW-Authenticate": 'Basic realm="Nextcloud"'})
        path, body = request.url.path, request.content.decode()
        if self.home and path.startswith(CALENDARS) and request.url.host != httpx.URL(self.home).host:
            return httpx.Response(404)  # asked of the principal's host: not where this home lives
        if path.startswith(CALENDARS) and path.split("/")[-2] in self.forbidden and request.method in ("REPORT", "PUT"):
            return httpx.Response(403)
        if self.root_page and path == "/" and request.method == "PROPFIND":
            return httpx.Response(200, text="<!doctype html><title>Nextcloud</title>")
        if path.startswith("/.well-known/"):
            return httpx.Response(301, headers={"location": f"{DAV}/"})
        if request.method == "PROPFIND":
            return self.propfind(path, body)
        if request.method == "REPORT" and path.startswith(CALENDARS):
            return self.events(path.split("/")[-2], ET.fromstring(body))
        if request.method == "REPORT" and path == f"{BOOKS}contacts/":
            words = ET.fromstring(body).findtext(".//a:text-match", "", NS).lower()
            found = [card for card in self.cards if words in card.lower()]
            return multistatus(*(item(f"{path}{i}.vcf", "a:address-data", c) for i, c in enumerate(found)))
        if request.method == "PUT":
            self.put[path] = (body, request.headers)
            return httpx.Response(201)
        return httpx.Response(405)

    def propfind(self, path: str, body: str) -> httpx.Response:
        if "current-user-principal" in body:
            if not path.startswith("/remote.php/dav"):
                return httpx.Response(404)  # the host's root, not its DAV server
            return multistatus(response(path, href("d:current-user-principal", PRINCIPAL)))
        if path == PRINCIPAL and "calendar-home-set" in body:
            home = f"{self.home}{CALENDARS}" if self.home else CALENDARS
            return multistatus(response(path, href("c:calendar-home-set", home)))
        if path == PRINCIPAL:
            return multistatus(response(path, href("a:addressbook-home-set", BOOKS)))
        if path == CALENDARS:
            return multistatus(
                response(path, "<d:resourcetype><d:collection/></d:resourcetype>"),
                calendar("perso", "Perso", "VEVENT"),
                calendar("rappels", "Rappels", "VTODO"),
                calendar("travail", "Travail", "VEVENT"),
                response(f"{path}inbox/", "<d:resourcetype><d:collection/><c:schedule-inbox/></d:resourcetype>"),
            )
        return multistatus(
            response(path, "<d:resourcetype><d:collection/></d:resourcetype>"),
            response(f"{path}contacts/", "<d:resourcetype><d:collection/><a:addressbook/></d:resourcetype>"),
        )

    def events(self, name: str, query: ET.Element) -> httpx.Response:
        expand, span = query.find(".//c:expand", NS), query.find(".//c:time-range", NS)
        assert expand is not None and span is not None, "events are asked expanded, within a time range"
        start, end = span.get("start", "")[:8], span.get("end", "")[:8]
        found = [e for e in self.calendars.get(name, []) if start <= _day(e) < end]
        data = [f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{e}END:VCALENDAR\r\n" for e in found]
        return multistatus(*(item(f"{CALENDARS}{name}/{i}.ics", "c:calendar-data", d) for i, d in enumerate(data)))

    def propfinds(self) -> int:
        return sum(r.method == "PROPFIND" for r in self.requests)


def tools(dav: FakeDav, access: Access | None = None) -> dict[str, Any]:
    connector = DavConnector(transport=dav.transport)
    return {t.name: t for t in connector.tools(CONNECTION, access or DavAccess())}


async def run(dav: FakeDav, name: str, **arguments: Any) -> Any:
    return await tools(dav)[name].run(arguments, CONTEXT)


def test_only_adding_an_event_writes() -> None:
    found = tools(FakeDav())
    assert {name for name, tool in found.items() if tool.risk is not Risk.READ} == {"dav_calendar_create"}
    assert sorted(n for s in INFO.services for n in s.tools) == sorted(found)


async def test_events_of_every_calendar_come_in_order_with_their_text_unescaped() -> None:
    dav = FakeDav()
    dav.calendars["perso"] = [
        vevent("Dentiste", ":20261114T140000Z", ":20261114T143000Z", location="12 rue Victor Hugo\\, Lyon"),
        vevent("Férié", ";VALUE=DATE:20261111", ";VALUE=DATE:20261112"),
    ]
    dav.calendars["travail"] = [
        vevent("Réunion", ":20261113T080000Z", ":20261113T090000Z", attendee="mailto:lea@x.fr",
               description="Ordre du jour :\\n1. budget\r\n  2. planning"),
    ]  # fmt: skip
    found = await run(dav, "dav_calendar_events", since="2026-11-10T00:00:00+01:00", until="2026-11-20T00:00:00+01:00")
    assert [(e["calendar"], e["title"], e["start"]) for e in found["events"]] == [
        ("Perso", "Férié", "2026-11-11"),
        ("Travail", "Réunion", "2026-11-13T08:00:00+00:00"),
        ("Perso", "Dentiste", "2026-11-14T14:00:00+00:00"),
    ]
    meeting = found["events"][1]
    assert meeting["attendees"] == ["lea@x.fr"] and meeting["description"] == "Ordre du jour :\n1. budget 2. planning"
    assert found["events"][2]["location"] == "12 rue Victor Hugo, Lyon" and found["events"][0]["all_day"]
    assert not any("rappels" in r.url.path for r in dav.requests)  # a list of tasks is not a calendar of events


async def test_an_event_is_put_as_a_new_item_in_the_calendar_named() -> None:
    dav = FakeDav()
    made = await run(dav, "dav_calendar_create", title="Dîner; chez Mamie", start="2026-11-20T19:30:00+01:00",
                     end="2026-11-20T22:00:00+01:00", calendar="travail")  # fmt: skip
    await run(dav, "dav_calendar_create", title="Vacances", start="2026-12-21", end="2027-01-04")
    (dinner_path, (dinner, headers)), (holiday_path, (holiday, _)) = dav.put.items()
    assert dinner_path.startswith("/remote.php/dav/calendars/mathis/travail/") and headers["if-none-match"] == "*"
    assert "DTSTART:20261120T183000Z" in dinner and r"SUMMARY:Dîner\; chez Mamie" in dinner
    assert holiday_path.startswith("/remote.php/dav/calendars/mathis/perso/")  # the first calendar of events
    assert "DTSTART;VALUE=DATE:20261221" in holiday and "DTEND;VALUE=DATE:20270104" in holiday
    assert made["event"]["title"] == "Dîner; chez Mamie" and made["event"]["calendar"] == "Travail"


async def test_a_calendar_that_does_not_exist_is_named_among_those_that_do() -> None:
    with pytest.raises(ToolFailed, match="Perso, Travail"):
        await run(FakeDav(), "dav_calendar_create", title="x", start="2026-12-21", end="2026-12-22", calendar="Sport")


async def test_contacts_are_read_with_their_structured_fields() -> None:
    dav = FakeDav()
    jeanne = (
        "FN:Mamie Jeanne",
        "item1.EMAIL;TYPE=INTERNET:jeanne@x.fr",  # a group, as Apple writes them
        "TEL;TYPE=CELL:+33 6 12 34 56 78",
        "ADR;TYPE=HOME:;;3 place Bellecour\\; bâtiment B;Lyon;;69002;France",
        "BDAY:--0309",
        "ORG:Retraitée;Bénévolat",
    )
    dav.cards = [vcard(*jeanne), vcard("FN:Plombier", "TEL:+33 4 00 00 00 00")]
    found = await run(dav, "dav_contacts_search", query="Jeanne")
    assert found["contacts"] == [
        {
            "name": "Mamie Jeanne",
            "emails": ["jeanne@x.fr"],
            "phones": ["+33 6 12 34 56 78"],
            "addresses": ["3 place Bellecour; bâtiment B, Lyon, 69002, France"],
            "birthday": "03-09",
            "company": "Retraitée",
        }
    ]


async def test_a_server_address_without_dav_is_found_through_its_well_known_address_once() -> None:
    dav = FakeDav()
    access = DavAccess(server=f"{HOST}/")
    connector = DavConnector(transport=dav.transport)
    events = next(t for t in connector.tools(CONNECTION, access) if t.name == "dav_calendar_events")
    for _ in range(2):
        await events.run({"since": "2026-11-10T00:00:00Z", "until": "2026-11-11T00:00:00Z"}, CONTEXT)
    assert any(r.url.path == "/.well-known/caldav" for r in dav.requests)
    found_once = dav.propfinds()
    await events.run({"since": "2026-11-10T00:00:00Z", "until": "2026-11-11T00:00:00Z"}, CONTEXT)
    assert dav.propfinds() == found_once


async def test_connecting_checks_the_login_and_refuses_a_password_in_clear() -> None:
    dav = FakeDav()
    async with DavConnector(transport=dav.transport) as connector:
        assert await connector.identify(DavAccess()) == "mathis"
        with pytest.raises(ProviderError, match="refused the login") as refused:
            await connector.identify(DavAccess(password="wrong"))
        assert not refused.value.transient
        with pytest.raises(ProviderError, match="must use https"):
            await connector.identify(DavAccess(server="http://cloud.example/remote.php/dav"))


async def test_calendars_on_another_host_are_reached_there() -> None:
    dav = FakeDav()
    dav.home = "https://p52-caldav.example"  # the principal names an absolute home, its calendars path-only hrefs
    found = await run(dav, "dav_calendar_events", since="2026-11-10T00:00:00Z", until="2026-11-11T00:00:00Z")
    assert found["events"] == []
    reports = [r.url for r in dav.requests if r.method == "REPORT"]
    assert reports and all(u.host == "p52-caldav.example" for u in reports)


async def test_a_calendar_that_refuses_leaves_the_others_read_and_written() -> None:
    dav = FakeDav()
    dav.forbidden = {"perso"}
    dav.calendars["travail"] = [vevent("Réunion", ":20261113T080000Z", ":20261113T090000Z")]
    found = await run(dav, "dav_calendar_events", since="2026-11-10T00:00:00Z", until="2026-11-20T00:00:00Z")
    assert [e["title"] for e in found["events"]] == ["Réunion"] and found["unreadable_calendars"] == ["Perso"]
    made = await run(dav, "dav_calendar_create", title="Vacances", start="2026-12-21", end="2027-01-04")
    assert made["event"]["calendar"] == "Travail", "the first calendar that takes it"


async def test_a_server_root_that_answers_a_web_page_is_found_through_its_well_known_address() -> None:
    dav = FakeDav()
    dav.root_page = True
    connector = DavConnector(transport=dav.transport)
    events = next(
        t for t in connector.tools(CONNECTION, DavAccess(server=f"{HOST}/")) if t.name == "dav_calendar_events"
    )
    await events.run({"since": "2026-11-10T00:00:00Z", "until": "2026-11-11T00:00:00Z"}, CONTEXT)
    assert any(r.url.path == "/.well-known/caldav" for r in dav.requests)
