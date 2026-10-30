"""Connections from the admin: OAuth with PKCE, fresh tokens, consent for writes, clean unplugging."""

import asyncio
import base64
import hashlib
import json
import urllib.parse

import pytest

from nestor.core import ContractError, PersonId, ProviderError
from nestor.core.i18n import Message
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.connectors import (
    AuthKind,
    ConnectedInbound,
    ConnectionChanged,
    ConnectionCreated,
    ConnectionRemoved,
    Connections,
    ConnectorTools,
    Status,
)
from nestor.modules.initiative import Incoming
from nestor.modules.journal import Journal, LogQuery
from nestor.testing.connectors import FakeProvider, MemoryVault, ScriptedConnector
from nestor.testing.journal import MemoryEventLog

MATHIS = PersonId("mathis")
REDIRECT = "https://nestor.example/connections/callback"
CONTEXT = ToolContext(address=Address("telegram", "42"), person=MATHIS)


class Setup:
    def __init__(self, *, lifetime_s: float = 3600.0) -> None:
        self.journal = Journal(MemoryEventLog())
        self.vault = MemoryVault()
        self.provider = FakeProvider(lifetime_s=lifetime_s)
        self.mail = ScriptedConnector()
        self.imap = ScriptedConnector("imap", auth=AuthKind.SECRET, account="mathilde@free.fr")
        self.connections = Connections(self.journal, self.vault, self.provider, [self.mail, self.imap])

    async def connect(self) -> str:
        await self.connections.set_client("mailbox", "client-123", "s3cret")
        url = await self.connections.begin("mailbox", MATHIS, REDIRECT)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        verifier = next(iter(self.connections._pending.values())).verifier  # what only Nestor knows
        code = self.provider.authorize(query["client_id"], verifier)
        connection = await self.connections.complete(query["state"], code)
        return connection.id


async def test_the_authorization_url_carries_pkce_state_and_scopes() -> None:
    setup = Setup()
    await setup.connections.set_client("mailbox", "client-123", "s3cret")
    url = await setup.connections.begin("mailbox", MATHIS, REDIRECT)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    verifier = next(iter(setup.connections._pending.values())).verifier

    assert url.startswith("https://provider.example/authorize?")
    assert (query["client_id"], query["redirect_uri"], query["scope"]) == ("client-123", REDIRECT, "mail.read")
    assert query["code_challenge_method"] == "S256" and query["access_type"] == "offline"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == expected
    assert len(query["state"]) >= 32


async def test_completing_the_flow_records_the_account_and_never_logs_secrets() -> None:
    setup = Setup()
    connection_id = await setup.connect()

    connection = setup.connections.connections[connection_id]
    assert (connection.account, connection.owner, connection.status) == ("mathis@example.com", MATHIS, Status.CONNECTED)
    logged = json.dumps([e.record for e in await setup.journal.log.read(LogQuery())])
    tokens = await setup.vault.get(connection_id, "tokens")
    assert tokens and tokens["access_token"] not in logged and tokens["refresh_token"] not in logged
    assert "s3cret" not in logged
    assert len(await setup.journal.history(ConnectionCreated)) == 1


async def test_a_forged_or_replayed_callback_is_refused() -> None:
    setup = Setup()
    await setup.connect()
    with pytest.raises(ContractError, match="unknown or expired"):
        await setup.connections.complete("forged-state", "code")


async def test_a_code_obtained_with_another_verifier_is_refused_and_nothing_is_kept() -> None:
    setup = Setup()
    await setup.connections.set_client("mailbox", "client-123", "s3cret")
    url = await setup.connections.begin("mailbox", MATHIS, REDIRECT)
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["state"]
    with pytest.raises(ProviderError, match="invalid_grant"):
        await setup.connections.complete(state, setup.provider.authorize("client-123", "stolen-verifier"))
    assert setup.connections.connections == {}


async def test_oauth_needs_the_household_client_first() -> None:
    setup = Setup()
    assert not await setup.connections.has_client("mailbox")
    with pytest.raises(ContractError, match="register an OAuth client"):
        await setup.connections.begin("mailbox", MATHIS, REDIRECT)
    with pytest.raises(ContractError, match="does not connect through OAuth"):
        await setup.connections.set_client("imap", "x", "y")
    with pytest.raises(ContractError, match="no connector 'slack'"):
        await setup.connections.begin("slack", MATHIS, REDIRECT)


async def test_an_expired_token_is_refreshed_before_use() -> None:
    setup = Setup(lifetime_s=0)
    connection_id = await setup.connect()
    tools = {t.name: t for t in ConnectorTools(setup.connections).tools()}

    assert await tools["mailbox_search"].run({"query": "colis"}, CONTEXT) == "2 mails about colis"
    assert setup.provider.refreshes == 2  # once when identifying, once for the search
    assert (await setup.vault.get(connection_id, "tokens") or {})["refresh_token"], "refresh token kept"


async def test_a_refused_refresh_asks_the_person_to_reconnect_and_hides_the_tools() -> None:
    setup = Setup()
    connection_id = await setup.connect()
    setup.provider.lifetime_s = 0
    await setup.vault.put(
        connection_id,
        "tokens",
        {**(await setup.vault.get(connection_id, "tokens") or {}), "expires_at": "2000-01-01T00:00:00+00:00"},
    )
    setup.provider.refusing = True
    search = {t.name: t for t in ConnectorTools(setup.connections).tools()}["mailbox_search"]

    with pytest.raises(ProviderError):
        await search.run({"query": "x"}, CONTEXT)
    assert setup.connections.connections[connection_id].status is Status.NEEDS_REAUTH
    assert ConnectorTools(setup.connections).tools() == []
    assert (await setup.journal.history(ConnectionChanged))[-1].reason == Message.of("connection-refresh-refused")
    assert setup.connections.connections[connection_id].status_reason == Message.of("connection-refresh-refused")


async def test_a_provider_outage_during_refresh_does_not_disconnect() -> None:
    setup = Setup()
    connection_id = await setup.connect()
    await setup.vault.put(
        connection_id,
        "tokens",
        {**(await setup.vault.get(connection_id, "tokens") or {}), "expires_at": "2000-01-01T00:00:00+00:00"},
    )
    setup.provider.unreachable = True
    with pytest.raises(ProviderError):
        await setup.connections.access(setup.connections.connections[connection_id]).token()
    assert setup.connections.connections[connection_id].status is Status.CONNECTED


async def test_writing_tools_wait_for_the_persons_consent() -> None:
    setup = Setup()
    await setup.connect()
    send = {t.name: t for t in ConnectorTools(setup.connections).tools()}["mailbox_send"]

    properties = send.spec.parameters["properties"]
    assert isinstance(properties, dict) and "confirmed" in properties
    with pytest.raises(ToolFailed, match="ask the person to confirm"):
        await send.run({"to": "maman"}, CONTEXT)
    assert setup.mail.sent == []
    assert await send.run({"to": "maman", "confirmed": True}, CONTEXT) == "sent"
    assert setup.mail.sent == [{"to": "maman"}]


async def test_tools_can_be_disabled_per_connection_and_survive_a_restart() -> None:
    setup = Setup()
    connection_id = await setup.connect()
    await setup.connections.configure(connection_id, disabled_tools=["mailbox_send"], confirm_writes=False)

    restarted = Connections(setup.journal, setup.vault, setup.provider, [setup.mail, setup.imap])
    await restarted.start()
    assert [t.name for t in ConnectorTools(restarted).tools()] == ["mailbox_search"]
    assert restarted.connections[connection_id].confirm_writes is False


async def test_unplugging_revokes_at_the_provider_and_forgets_everything() -> None:
    setup = Setup()
    connection_id = await setup.connect()
    refresh = (await setup.vault.get(connection_id, "tokens") or {})["refresh_token"]
    await setup.connections.disconnect(connection_id)

    assert setup.provider.revoked == [refresh]
    assert await setup.vault.get(connection_id, "tokens") is None
    assert connection_id not in setup.connections.connections
    assert len(await setup.journal.history(ConnectionRemoved)) == 1
    restarted = Connections(setup.journal, setup.vault, setup.provider, [setup.mail])
    await restarted.start()
    assert restarted.connections == {}
    with pytest.raises(ContractError, match="no connection"):
        await setup.connections.disconnect(connection_id)


async def test_a_secret_based_service_connects_with_its_fields() -> None:
    setup = Setup()
    with pytest.raises(ContractError, match="missing: password"):
        await setup.connections.connect("imap", PersonId("mathilde"), {})
    with pytest.raises(ContractError, match="connects through OAuth"):
        await setup.connections.connect("mailbox", MATHIS, {"password": "x"})
    connection = await setup.connections.connect("imap", PersonId("mathilde"), {"password": "app-password"})
    assert connection.account == "mathilde@free.fr"
    assert await setup.vault.get(connection.id, "secrets") == {"password": "app-password"}


async def test_optional_fields_take_their_default() -> None:
    from nestor.core.i18n import Message
    from nestor.modules.connectors import ConnectorInfo, SecretField

    setup = Setup()
    setup.imap.info = ConnectorInfo(
        kind="imap",
        title=Message.of("connector-imap-title"),
        description=Message.of("connector-imap-description"),
        auth=AuthKind.SECRET,
        fields=(
            SecretField(name="password", label=Message.of("connector-imap-field-password")),
            SecretField(name="folder", label=Message.of("connector-imap-field-folder"), secret=False, default="INBOX"),
        ),
    )
    connection = await setup.connections.connect("imap", MATHIS, {"password": "x", "folder": ""})
    assert await setup.vault.get(connection.id, "secrets") == {"password": "x", "folder": "INBOX"}


async def test_inbound_items_flow_from_connections_plugged_in_while_running() -> None:
    setup = Setup()
    inbound = ConnectedInbound(setup.connections)
    assert inbound.kinds == ("mail",)
    feed = inbound.items()
    first = asyncio.ensure_future(anext(feed))
    await asyncio.sleep(0.01)
    connection_id = await setup.connect()  # plugged in from the admin, Nestor running
    await asyncio.sleep(0.01)
    setup.mail.inbox.deliver(Incoming(source="mailbox", kind="mail", title="Votre colis"))
    assert (await asyncio.wait_for(first, 1)).title == "Votre colis"

    await setup.connections.disconnect(connection_id)
    await asyncio.sleep(0.01)
    assert inbound._feeds == {}, "an unplugged account is no longer followed"
    await feed.aclose()
