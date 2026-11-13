"""A CalDAV and CardDAV account (RFC 4791, RFC 6352): finding its calendars and address books, and the few requests
the tools make, over HTTPS with the account's login and app password."""

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from nestor.adapters.connectors.common import StatusError
from nestor.core import ProviderError
from nestor.modules.connectors import Secrets

log = logging.getLogger(__name__)

PROVIDER = "dav"
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "a": "urn:ietf:params:xml:ns:carddav"}
XML = {"Content-Type": "application/xml; charset=utf-8"}


@dataclass(frozen=True, slots=True, kw_only=True)
class DavAccount:
    calendars: str  # the CalDAV server, as the person typed it
    contacts: str  # the CardDAV server: the same one, unless the provider has another (iCloud)
    username: str
    password: str

    @classmethod
    def of(cls, secrets: Secrets) -> "DavAccount":
        """`ProviderError(transient=False)` when the settings cannot work: the person must change them."""
        calendars = secrets.get("server", "").strip()
        contacts = secrets.get("contacts_server", "").strip() or calendars
        for url in (calendars, contacts):
            parts = urllib.parse.urlsplit(url)
            if parts.scheme not in ("https", "http") or not parts.hostname:
                raise ProviderError(PROVIDER, f"{url!r} is not an address (https://…)", transient=False)
            if parts.scheme == "http" and parts.hostname not in LOOPBACK:  # passwords never cross a network in clear
                raise ProviderError(PROVIDER, f"{url} must use https", transient=False)
        return cls(
            calendars=calendars,
            contacts=contacts,
            username=secrets.get("username", "").strip(),
            password=secrets.get("password", ""),
        )


@dataclass(frozen=True, slots=True)
class Collection:
    url: str
    name: str


class DavError(StatusError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(PROVIDER, status, "", message)


class Dav:
    """The account's collections, found once and kept while the connector runs."""

    def __init__(self, account: DavAccount, client: httpx.AsyncClient) -> None:
        self.account, self._client = account, client
        self._found: dict[str, list[Collection]] = {}

    async def calendars(self) -> list[Collection]:
        """The calendars that hold events (not only tasks)."""
        return await self._collections("c", self.account.calendars, "calendar-home-set", "calendar", "caldav")

    async def address_books(self) -> list[Collection]:
        return await self._collections("a", self.account.contacts, "addressbook-home-set", "addressbook", "carddav")

    async def report(self, url: str, body: str) -> list[tuple[str, str]]:
        """A `REPORT` on a collection: the href and the data (calendar or address) of each item it answers."""
        tree = await self._xml("REPORT", url, body, depth="1")
        found = []
        for response in tree.iterfind("d:response", NS):
            data = response.find(".//c:calendar-data", NS)
            if data is None:
                data = response.find(".//a:address-data", NS)
            if data is not None and data.text:
                found.append((response.findtext("d:href", "", NS), data.text))
        return found

    async def put(self, url: str, body: str, media_type: str) -> None:
        """A new item; never one that exists (`If-None-Match: *`)."""
        await self._request("PUT", url, body, {"Content-Type": media_type, "If-None-Match": "*"})

    async def _collections(self, ns: str, server: str, home_set: str, kind: str, service: str) -> list[Collection]:
        if kind in self._found:
            return self._found[kind]
        principal = await self._principal(server, service)
        prop = f'<d:propfind xmlns:d="DAV:" xmlns:{ns}="{NS[ns]}"><d:prop><{ns}:{home_set}/></d:prop></d:propfind>'
        home = (await self._xml("PROPFIND", principal, prop, depth="0")).find(f".//{ns}:{home_set}/d:href", NS)
        if home is None or not home.text:
            raise ProviderError(PROVIDER, f"{server} names no {kind} home for this account", transient=False)
        props = (
            f'<d:propfind xmlns:d="DAV:" xmlns:c="{NS["c"]}"><d:prop><d:resourcetype/><d:displayname/>'
            "<c:supported-calendar-component-set/></d:prop></d:propfind>"
        )
        home_url = urllib.parse.urljoin(principal, home.text)  # on another host, sometimes (iCloud's partitions)
        tree = await self._xml("PROPFIND", home_url, props, depth="1")
        found = []
        for response in tree.iterfind("d:response", NS):
            if response.find(f".//d:resourcetype/{ns}:{kind}", NS) is None:
                continue
            components = {c.get("name") for c in response.iterfind(".//c:supported-calendar-component-set/c:comp", NS)}
            if kind == "calendar" and components and "VEVENT" not in components:
                continue  # a list of tasks or reminders
            url = urllib.parse.urljoin(home_url, response.findtext("d:href", "", NS))  # against what was asked
            name = response.findtext(".//d:displayname", "", NS) or url.rstrip("/").rpartition("/")[2]
            found.append(Collection(url, name))
        self._found[kind] = found
        return found

    async def _principal(self, server: str, service: str) -> str:
        """Where the account's homes are named: asked of the server, then of its well-known address (RFC 6764)."""
        body = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
        for url in (server, urllib.parse.urljoin(server, f"/.well-known/{service}")):
            try:
                tree = await self._xml("PROPFIND", url, body, depth="0")
            except DavError as error:
                if error.transient:
                    raise
                continue  # not the right address: the next one
            href = tree.findtext(".//d:current-user-principal/d:href", "", NS)
            if href:
                return urllib.parse.urljoin(url, href)
        raise ProviderError(PROVIDER, f"{server} does not answer as a CalDAV or CardDAV server", transient=False)

    async def _xml(self, method: str, url: str, body: str, *, depth: str) -> ET.Element:
        response = await self._request(method, url, body, {**XML, "Depth": depth})
        try:
            return ET.fromstring(response.content)
        except ET.ParseError:  # a web page, say: not the address of a DAV server
            raise DavError(response.status_code, f"{url} answered with something other than XML") from None

    async def _request(self, method: str, url: str, body: str, headers: Mapping[str, str]) -> httpx.Response:
        auth = httpx.BasicAuth(self.account.username, self.account.password)
        try:
            response = await self._client.request(method, url, content=body.encode(), headers=headers, auth=auth)
        except httpx.HTTPError as error:
            raise ProviderError(PROVIDER, f"unreachable ({type(error).__name__})", transient=True) from None
        if response.status_code == 401:
            raise ProviderError(PROVIDER, "the server refused the login and app password", transient=False)
        if response.is_error:
            raise DavError(response.status_code, response.reason_phrase)
        return response


def new_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, transport=transport, follow_redirects=True)
