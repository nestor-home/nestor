"""Google (Gmail) connector: the inbound contract against a fake Gmail API, then what only Gmail can
break (expired history, rate limits, revoked authorisation) and what the model reads through the tools."""

import asyncio
import base64
import json
import logging
import urllib.parse
from collections.abc import Callable, Mapping
from typing import Any

import httpx
import pytest

from nestor.adapters.connectors.common import Backoff
from nestor.adapters.connectors.google import INFO, Every, GmailInbound, GoogleConnector, GoogleSettings, plugin
from nestor.core import PersonId, ProviderError
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import Risk, ToolContext, ToolFailed
from nestor.modules.connectors import Access, AuthKind, Connection, Connections, ConnectorTools, Secrets
from nestor.modules.initiative import Incoming
from nestor.modules.journal import Journal
from nestor.runtime import Services
from nestor.testing.connectors import FakeProvider, MemoryVault
from nestor.testing.initiative import InboundEventSourceContract
from nestor.testing.journal import MemoryEventLog

MATHIS = PersonId("mathis")
CONNECTION = Connection(kind="google", owner=MATHIS, account="mathis@gmail.com", id="gmail-math")
CONTEXT = ToolContext(address=Address("telegram", "42"), person=MATHIS)
TOKEN = "ya29.a0AfB_sentinel-access-token"
REDIRECT = "https://nestor.example/connections/callback"


def b64url(text: str, charset: str = "utf-8") -> str:
    return base64.urlsafe_b64encode(text.encode(charset)).decode().rstrip("=")


def part(mime_type: str, text: str, *, charset: str = "utf-8", filename: str = "") -> dict[str, Any]:
    return {
        "partId": "0",
        "mimeType": mime_type,
        "filename": filename,
        "headers": [{"name": "Content-Type", "value": f'{mime_type}; charset="{charset}"'}],
        "body": {"size": len(text), "data": b64url(text, charset)},
    }


def alternative(plain: str | None, html: str | None) -> dict[str, Any]:
    parts = [p for p in (plain and part("text/plain", plain), html and part("text/html", html)) if p]
    return {"mimeType": "multipart/alternative", "filename": "", "headers": [], "body": {"size": 0}, "parts": parts}


class FakeGmail:
    """Plays the Gmail API for one mailbox: a history of added messages with increasing, non-contiguous
    ids, pages of `page_size` records, history older than `oldest` forgotten (404), scripted failures."""

    def __init__(self, *, page_size: int = 2) -> None:
        self.page_size = page_size
        self.history_id = 4100
        self.oldest = 0
        self.records: list[tuple[int, str]] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.failures: list[httpx.Response] = []  # answered, in order, to the next history requests
        self.message_failures: list[httpx.Response] = []  # same, for the next message requests
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def deliver(
        self,
        subject: str,
        *,
        sender: str = "Colissimo <noreply@colissimo.fr>",
        plain: str | None = "Votre colis arrive demain.",
        html: str | None = "<p>Votre colis arrive <b>demain</b>.</p>",
        payload: dict[str, Any] | None = None,
    ) -> str:
        message_id = f"18c{len(self.records):05x}e2a9f"
        self.history_id += 7
        body = payload or {
            "mimeType": "multipart/mixed",
            "filename": "",
            "body": {"size": 0},
            "parts": [alternative(plain, html)],
        }
        body["headers"] = [
            {"name": "From", "value": sender},
            {"name": "To", "value": "mathis@gmail.com"},
            {"name": "Subject", "value": subject},
            {"name": "Date", "value": "Fri, 30 Oct 2026 09:12:00 +0100"},
            *body.get("headers", []),
        ]
        self.messages[message_id] = {
            "id": message_id,
            "threadId": f"t{message_id}",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "Votre colis arrive demain &amp; sera livré",
            "historyId": str(self.history_id),
            "internalDate": "1793347920000",
            "payload": body,
            "sizeEstimate": 4096,
        }
        self.records.append((self.history_id, message_id))
        return message_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return error(401, "authError", "Request had invalid authentication credentials.")
        path = request.url.path.removeprefix("/gmail/v1/users/me/")
        query = dict(urllib.parse.parse_qsl(request.url.query.decode()))
        if path == "profile":
            return httpx.Response(200, json=self.profile())
        if path == "history":
            if self.failures:
                return self.failures.pop(0)
            return self.history(int(query["startHistoryId"]), int(query.get("pageToken", "0")))
        if path == "messages":
            return self.search(query["q"], int(query["maxResults"]))
        if self.message_failures:
            return self.message_failures.pop(0)
        message = self.messages.get(path.removeprefix("messages/"))
        if message is None:
            return error(404, "notFound", "Requested entity was not found.")
        if query.get("format") == "metadata":
            wanted = {h.lower() for h in request.url.params.get_list("metadataHeaders")}
            headers = [h for h in message["payload"]["headers"] if h["name"].lower() in wanted]
            return httpx.Response(200, json={**message, "payload": {"headers": headers}})
        return httpx.Response(200, json=message)

    def profile(self) -> dict[str, Any]:
        return {
            "emailAddress": "mathis@gmail.com",
            "messagesTotal": 1234,
            "threadsTotal": 900,
            "historyId": str(self.history_id),
        }

    def history(self, start: int, offset: int) -> httpx.Response:
        if start < self.oldest:
            return error(404, "notFound", "Requested entity was not found.")
        after = [(h, m) for h, m in self.records if h > start]
        page = after[offset : offset + self.page_size]
        found: dict[str, Any] = {"historyId": str(self.history_id)}
        if page:
            found["history"] = [
                {
                    "id": str(h),
                    "messages": [{"id": m, "threadId": f"t{m}"}],
                    "messagesAdded": [{"message": {"id": m, "threadId": f"t{m}", "labelIds": ["INBOX", "UNREAD"]}}],
                }
                for h, m in page
            ]
        if offset + self.page_size < len(after):
            found["nextPageToken"] = str(offset + self.page_size)
        return httpx.Response(200, json=found)

    def search(self, query: str, limit: int) -> httpx.Response:
        ids = [i for i, m in reversed(self.messages.items()) if query.lower() in json.dumps(m).lower()][:limit]
        return httpx.Response(200, json={"messages": [{"id": i, "threadId": f"t{i}"} for i in ids]})

    def history_calls(self) -> int:
        return sum(r.url.path.endswith("/history") for r in self.requests)


def error(status: int, reason: str, message: str) -> httpx.Response:
    body = {"error": {"code": status, "message": message, "errors": [{"domain": "global", "reason": reason}]}}
    return httpx.Response(status, json=body)


class FakeAccess(Access):
    """The connection's access as Connections lends it: a token (or a refusal), durable state."""

    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.refusals = 0  # next token() calls that fail as a revoked authorisation does
        self.token_calls = 0

    async def token(self) -> str:
        self.token_calls += 1
        if self.refusals:
            self.refusals -= 1
            raise ProviderError("google", "authorisation expired: connect again", transient=False)
        return TOKEN

    async def secrets(self) -> Secrets:
        return {}

    async def load_state(self) -> Mapping[str, str]:
        return dict(self.state)

    async def save_state(self, state: Mapping[str, str]) -> None:
        self.state = dict(state)


def inbound(gmail: FakeGmail, access: FakeAccess, **options: Any) -> GmailInbound:
    options.setdefault("blocked_s", 0.01)
    return GmailInbound(CONNECTION, access, wakeup=Every(0.01), transport=gmail.transport, **options)


async def take(source: GmailInbound, count: int) -> list[Incoming]:
    feed = source.items()
    try:
        return [await asyncio.wait_for(anext(feed), 5.0) for _ in range(count)]
    finally:
        await feed.aclose()


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(5.0):
        while not condition():
            await asyncio.sleep(0.005)


class TestGmailInbound(InboundEventSourceContract):
    @pytest.fixture(autouse=True)
    def _mailbox(self) -> None:
        self.gmail, self.access = FakeGmail(), FakeAccess()

    def source(self) -> GmailInbound:
        return inbound(self.gmail, self.access)

    async def arrive(self, title: str) -> None:
        self.gmail.deliver(title)


# -- the inbound feed ---------------------------------------------------------------------------------


async def test_a_first_start_yields_only_mail_received_after_it() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    gmail.deliver("Ancienne facture")
    async with inbound(gmail, access) as source:
        gmail.deliver("Votre colis est en route")
        [item] = await take(source, 1)
    assert item.title == "Votre colis est en route"


async def test_an_item_carries_the_mail_its_connection_and_its_owner() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access) as source:
        message_id = gmail.deliver("Livraison de la poussette", sender="Colissimo <noreply@colissimo.fr>")
        [item] = await take(source, 1)
    assert (item.kind, item.source, item.owner, item.sender) == (
        "mail",
        "gmail-math",
        MATHIS,
        "Colissimo <noreply@colissimo.fr>",
    )
    assert item.body == "Votre colis arrive demain."
    assert item.data == {"message_id": message_id, "thread_id": f"t{message_id}"}
    assert item.at.isoformat() == "2026-10-30T08:12:00+00:00"


async def test_a_feed_stopped_in_the_middle_of_a_batch_resumes_with_the_next_mail() -> None:
    gmail, access = FakeGmail(page_size=2), FakeAccess()
    async with inbound(gmail, access) as first:
        for subject in ("un", "deux", "trois"):
            gmail.deliver(subject)
        assert [i.title for i in await take(first, 1)] == ["un"]
    async with inbound(gmail, access) as restarted:
        gmail.deliver("quatre")
        assert [i.title for i in await take(restarted, 3)] == ["deux", "trois", "quatre"]


async def test_the_cursor_moves_past_consumed_history_so_old_history_can_expire(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access) as source:
        feed = source.items()
        gmail.deliver("un")
        assert (await asyncio.wait_for(anext(feed), 5.0)).title == "un"
        pending = asyncio.ensure_future(anext(feed))
        await until(lambda: gmail.history_calls() >= 3)  # looked again after "un"
        gmail.oldest = gmail.history_id  # Gmail forgets everything up to now
        gmail.deliver("deux")
        assert (await asyncio.wait_for(pending, 5.0)).title == "deux"
        await feed.aclose()
    assert "no longer knows" not in caplog.text


async def test_a_message_that_cannot_be_read_yet_is_retried_rather_than_skipped() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    gmail.message_failures = [error(500, "backendError", "Backend Error")]
    async with inbound(gmail, access, backoff=Backoff(0.01)) as source:
        gmail.deliver("lu au second essai")
        assert [i.title for i in await take(source, 1)] == ["lu au second essai"]


async def test_the_connector_feeds_watches_with_its_poll_interval() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with GoogleConnector(poll_interval_s=0.01, transport=gmail.transport) as google:
        source = google.inbound(CONNECTION, access)
        assert source is not None and source.kinds == ("mail",)
        async with source:
            gmail.deliver("via le connecteur")
            feed = source.items()
            assert (await asyncio.wait_for(anext(feed), 5.0)).title == "via le connecteur"
            await feed.aclose()


async def test_mail_arriving_across_several_history_pages_comes_in_order() -> None:
    gmail, access = FakeGmail(page_size=2), FakeAccess()
    async with inbound(gmail, access) as source:
        subjects = [f"mail {n}" for n in range(5)]
        for subject in subjects:
            gmail.deliver(subject)
        assert [i.title for i in await take(source, 5)] == subjects


async def test_an_expired_history_cursor_resyncs_and_says_mail_was_skipped(caplog: pytest.LogCaptureFixture) -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access):
        pass
    gmail.deliver("reçu pendant une longue coupure")
    gmail.oldest = gmail.history_id  # Gmail forgot the history Nestor stopped at
    async with inbound(gmail, access) as restarted:
        feed = restarted.items()
        pending = asyncio.ensure_future(anext(feed))
        await until(lambda: "no longer knows history id" in caplog.text)
        gmail.deliver("après la reprise")
        assert (await asyncio.wait_for(pending, 5.0)).title == "après la reprise"
        await feed.aclose()
    assert "mail received in between is not yielded" in caplog.text


async def test_rate_limits_and_outages_are_retried_until_gmail_answers() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    gmail.failures = [
        error(429, "rateLimitExceeded", "Too many concurrent requests for user"),
        error(403, "userRateLimitExceeded", "User-rate limit exceeded"),
        httpx.Response(503, text="Service Unavailable"),
    ]
    async with inbound(gmail, access, backoff=Backoff(0.01, 0.04)) as source:
        gmail.deliver("après la limite")
        [item] = await take(source, 1)
    assert item.title == "après la limite"
    assert gmail.history_calls() == 4


async def test_a_revoked_authorisation_pauses_the_feed_until_the_person_reconnects(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access):
        pass
    access.refusals = 3
    async with inbound(gmail, access) as source:
        gmail.deliver("pendant la reconnexion")
        [item] = await take(source, 1)
    assert item.title == "pendant la reconnexion"
    assert caplog.text.count("paused until the account is reconnected") == 1
    assert "resumed" in caplog.text


async def test_a_source_started_while_gmail_is_down_draws_its_line_once_gmail_answers() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    access.refusals = 1
    async with inbound(gmail, access) as source:
        assert access.state == {}
        feed = source.items()
        pending = asyncio.ensure_future(anext(feed))
        await until(lambda: bool(access.state))
        gmail.deliver("premier")
        assert (await asyncio.wait_for(pending, 5.0)).title == "premier"
        await feed.aclose()


async def test_a_mail_deleted_before_it_is_read_is_skipped() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access) as source:
        deleted = gmail.deliver("supprimé aussitôt")
        del gmail.messages[deleted]
        gmail.deliver("gardé")
        assert [i.title for i in await take(source, 1)] == ["gardé"]


async def test_a_mail_without_text_parts_falls_back_to_its_snippet() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    async with inbound(gmail, access) as source:
        gmail.deliver("Photo", payload={"mimeType": "image/jpeg", "filename": "photo.jpg", "body": {"size": 9}})
        [item] = await take(source, 1)
    assert item.body == "Votre colis arrive demain & sera livré"


async def test_closing_a_waiting_feed_ends_it_and_releases_its_client() -> None:
    gmail, access = FakeGmail(), FakeAccess()
    source = inbound(gmail, access)
    await source.start()
    task = asyncio.ensure_future(anext(source.items()))
    await until(lambda: gmail.history_calls() >= 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await source.close()
    await source.close()
    calls = len(gmail.requests)
    await asyncio.sleep(0.05)
    assert len(gmail.requests) == calls


async def test_the_access_token_never_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    gmail, access = FakeGmail(), FakeAccess()
    gmail.failures = [error(500, "backendError", "Backend Error")]
    async with inbound(gmail, access, backoff=Backoff(0.01)) as source:
        gmail.deliver("secret ?")
        await take(source, 1)
    assert caplog.text and TOKEN not in caplog.text


# -- the tools ----------------------------------------------------------------------------------------


def tools(gmail: FakeGmail, access: Access | None = None, **options: Any) -> dict[str, Any]:
    connector = GoogleConnector(transport=gmail.transport, **options)
    return {t.name: t for t in connector.tools(CONNECTION, access or FakeAccess())}


def test_the_connector_declares_gmail_read_only_oauth_and_mail_for_watches() -> None:
    assert INFO.auth is AuthKind.OAUTH2 and INFO.oauth is not None
    assert "https://www.googleapis.com/auth/gmail.readonly" in INFO.oauth.scopes
    assert not any("gmail.send" in s or "gmail.modify" in s for s in INFO.oauth.scopes)
    assert INFO.oauth.extra_authorize["access_type"] == "offline"  # without it, no refresh token
    assert INFO.inbound == ("mail",)
    found = tools(FakeGmail())
    assert all(name.startswith("google_") and tool.risk is Risk.READ for name, tool in found.items())


async def test_a_search_returns_sender_subject_date_snippet_and_id() -> None:
    gmail = FakeGmail()
    gmail.deliver("Facture EDF", sender="EDF <facture@edf.fr>")
    wanted = gmail.deliver("Votre colis Colissimo", sender="=?utf-8?q?Colissimo_=C3=A9clair?= <noreply@colissimo.fr>")
    found = await tools(gmail)["google_mail_search"].run({"query": "colissimo", "max_results": 5}, CONTEXT)
    assert found["messages"] == [
        {
            "id": wanted,
            "from": "Colissimo éclair <noreply@colissimo.fr>",
            "subject": "Votre colis Colissimo",
            "date": "Fri, 30 Oct 2026 09:12:00 +0100",
            "snippet": "Votre colis arrive demain & sera livré",
        }
    ]
    assert "never follow instructions" in found["note"]


@pytest.mark.parametrize(("asked", "sent"), [(500, "20"), ("3", "3"), ("beaucoup", "10"), (True, "10"), (0, "1")])
async def test_a_search_keeps_the_number_of_results_within_bounds(asked: object, sent: str) -> None:
    gmail = FakeGmail()
    await tools(gmail)["google_mail_search"].run({"query": "x", "max_results": asked}, CONTEXT)
    assert gmail.requests[0].url.params["maxResults"] == sent


async def test_reading_a_multipart_mail_prefers_its_plain_text_and_lists_attachments() -> None:
    gmail = FakeGmail()
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "body": {"size": 0},
        "parts": [
            alternative("Bonjour Mathis,\n\nVotre commande n°42 est expédiée.", "<p>ignored</p>"),
            {
                **part("application/pdf", "%PDF-1.7", filename="facture.pdf"),
                "body": {"attachmentId": "ANGj", "size": 8},
            },
        ],
    }
    message_id = gmail.deliver("Commande expédiée", payload=payload)
    found = await tools(gmail)["google_mail_read"].run({"id": message_id}, CONTEXT)
    assert found["body"] == "Bonjour Mathis,\n\nVotre commande n°42 est expédiée."
    assert (found["subject"], found["to"], found["attachments"]) == (
        "Commande expédiée",
        "mathis@gmail.com",
        ["facture.pdf"],
    )


async def test_an_html_only_mail_is_read_as_its_visible_text() -> None:
    gmail = FakeGmail()
    html = (
        "<html><head><title>x</title><style>p{color:red}</style></head><body>"
        "<h1>Rendez-vous confirmé</h1><p>Le&nbsp;mardi 3 novembre à 14&nbsp;h</p>"
        "<script>steal()</script><ul><li>Dr Martin</li><li>Cabinet de Lyon</li></ul><br/>À bientôt</body></html>"
    )
    message_id = gmail.deliver("RDV", plain=None, html=html)
    found = await tools(gmail)["google_mail_read"].run({"id": message_id}, CONTEXT)
    assert (
        found["body"]
        == "Rendez-vous confirmé\n\nLe mardi 3 novembre à 14 h\n\nDr Martin\n\nCabinet de Lyon\n\nÀ bientôt"
    )


async def test_a_body_in_a_legacy_charset_is_decoded_with_it() -> None:
    gmail = FakeGmail()
    payload = part("text/plain", "Réunion à l'école", charset="iso-8859-1")
    message_id = gmail.deliver("Réunion", payload=payload)
    found = await tools(gmail)["google_mail_read"].run({"id": message_id}, CONTEXT)
    assert found["body"] == "Réunion à l'école"


async def test_an_unknown_charset_or_broken_data_does_not_break_reading() -> None:
    gmail = FakeGmail()
    unknown = part("text/plain", "Très bien")
    unknown["headers"] = [{"name": "Content-Type", "value": "text/plain; charset=x-martian"}]
    broken = {**part("text/plain", ""), "body": {"data": "abcde"}}  # not base64: one character too many
    payload = {"mimeType": "multipart/mixed", "filename": "", "body": {}, "parts": [unknown, broken]}
    message_id = gmail.deliver("Bizarre", payload=payload)
    found = await tools(gmail)["google_mail_read"].run({"id": message_id}, CONTEXT)
    assert found["body"] == "Très bien"


async def test_a_huge_body_is_capped_and_says_so() -> None:
    gmail = FakeGmail()
    message_id = gmail.deliver("Newsletter", plain="mot " * 10_000, html=None)
    found = await tools(gmail, body_chars=1000)["google_mail_read"].run({"id": message_id}, CONTEXT)
    assert len(found["body"]) < 1100
    assert found["body"].endswith("[truncated: 38999 more characters]")


async def test_reading_an_unknown_or_missing_id_tells_the_model_why() -> None:
    read = tools(FakeGmail())["google_mail_read"]
    with pytest.raises(ToolFailed, match="no message 'nope'"):
        await read.run({"id": "nope"}, CONTEXT)
    with pytest.raises(ToolFailed, match="give the id"):
        await read.run({}, CONTEXT)


async def test_tools_report_a_gmail_outage_or_a_revoked_authorisation_as_tool_failures() -> None:
    down = FakeGmail()
    down.transport = httpx.MockTransport(lambda request: httpx.Response(500, text="<html>oops</html>"))
    with pytest.raises(ToolFailed, match="HTTP 500"):
        await tools(down)["google_mail_search"].run({"query": "x"}, CONTEXT)
    with pytest.raises(ToolFailed, match="HTTP 500"):
        await tools(down)["google_mail_read"].run({"id": "x"}, CONTEXT)
    revoked = FakeAccess()
    revoked.refusals = 2
    with pytest.raises(ToolFailed, match="connect again"):
        await tools(FakeGmail(), revoked)["google_mail_search"].run({"query": "x"}, CONTEXT)
    with pytest.raises(ToolFailed, match="connect again"):
        await tools(FakeGmail(), revoked)["google_mail_read"].run({"id": "x"}, CONTEXT)


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(200, text="not json"), "other than JSON"),
        (httpx.Response(200, json=["a list"]), "unexpected JSON"),
        (httpx.Response(403, json={"error": {"code": 403, "message": "Gmail disabled", "status": "PERMISSION_DENIED"}}),
         "PERMISSION_DENIED"),
    ],
)  # fmt: skip
async def test_unexpected_answers_become_readable_failures(response: httpx.Response, reason: str) -> None:
    gmail = FakeGmail()
    gmail.transport = httpx.MockTransport(lambda request: response)
    with pytest.raises(ToolFailed, match=reason):
        await tools(gmail)["google_mail_search"].run({"query": "x"}, CONTEXT)


async def test_an_unreachable_gmail_is_a_transient_provider_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    connector = GoogleConnector(transport=httpx.MockTransport(refuse))
    with pytest.raises(ProviderError) as raised:
        await connector.identify(FakeAccess())
    assert raised.value.transient


# -- connecting a Google account ----------------------------------------------------------------------


async def test_connecting_through_oauth_names_the_account_by_its_gmail_address() -> None:
    gmail = FakeGmail()
    gmail.transport = httpx.MockTransport(lambda r: gmail.handle(_with_token(r)))
    provider = FakeProvider()
    async with GoogleConnector(transport=gmail.transport) as google:
        connections = Connections(Journal(MemoryEventLog()), MemoryVault(), provider, [google])
        await connections.set_client("google", "1234.apps.googleusercontent.com", "GOCSPX-secret")
        url = await connections.begin("google", MATHIS, REDIRECT)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert query["scope"] == "openid email https://www.googleapis.com/auth/gmail.readonly"
        assert query["prompt"] == "consent" and query["include_granted_scopes"] == "true"
        code = provider.authorize(query["client_id"], next(iter(connections._pending.values())).verifier)
        connection = await connections.complete(query["state"], code)
        assert connection.account == "mathis@gmail.com"
        search, read = ConnectorTools(connections).tools()
        assert (search.name, read.name) == ("google_mail_search", "google_mail_read")
        gmail.deliver("Bienvenue")
        found: Any = await search.run({"query": "bienvenue"}, CONTEXT)
        assert [m["subject"] for m in found["messages"]] == ["Bienvenue"]


async def test_a_profile_without_an_address_cannot_be_connected() -> None:
    gmail = FakeGmail()
    gmail.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"historyId": "1"}))
    with pytest.raises(ProviderError, match="no email address"):
        await GoogleConnector(transport=gmail.transport).identify(FakeAccess())


def _with_token(request: httpx.Request) -> httpx.Request:
    """Connections hands out the provider's own tokens: the fake Gmail accepts any bearer here."""
    request.headers["authorization"] = f"Bearer {TOKEN}"
    return request


# -- the plugin ---------------------------------------------------------------------------------------


def test_the_plugin_builds_a_named_connector_from_its_settings(tmp_path: Any) -> None:
    connector = plugin.create({"poll_interval_s": 120}, "gmail", Services(data_dir=tmp_path))
    assert isinstance(connector, GoogleConnector)
    assert (connector.name, connector.poll_interval_s, connector.info.kind) == ("gmail", 120, "google")


def test_settings_reject_a_backoff_ceiling_below_its_start() -> None:
    with pytest.raises(ValueError, match="retry_max_s"):
        GoogleSettings(retry_initial_s=10, retry_max_s=1)
