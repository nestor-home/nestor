"""Plugging services in from the server-rendered pages: catalogue, OAuth client, consent, tools, unplugging.

The callback itself and its failures are the API's: `api/v1/test_connections`."""

import base64
import urllib.parse
from pathlib import Path

import httpx
import pytest

from nestor.modules.connectors import ConnectorTools, Status

from .harness import CLIENT_SECRET, Harness

RELAY = "https://nestor.mathislambert.fr/redirect/oauth"


async def register_client(admin: Harness) -> None:
    await admin.get("/connectors/mailbox")
    response = await admin.post(
        "/connectors/mailbox/client", {"client_id": "client-123", "client_secret": CLIENT_SECRET}
    )
    assert response.headers["location"] == "/connectors/mailbox"


async def start_flow(admin: Harness, person: str = "mathis", **extra: str) -> str:
    await admin.get("/connectors/mailbox")
    response = await admin.post("/connectors/mailbox/connect", {"person": person, **extra})
    assert response.status_code == 303
    return response.headers["location"]


async def connect_mailbox(admin: Harness) -> str:
    await register_client(admin)
    back = admin.consent(await start_flow(admin))
    response = await admin.get("/connections/callback", **back)
    assert response.status_code == 303, response.text
    return shown(response)


def shown(response: httpx.Response) -> str:
    """The connection a redirect shows: `/connections/<id>?connected=1`."""
    return urllib.parse.urlsplit(response.headers["location"]).path.rsplit("/", 1)[1]


def query(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


async def test_the_catalogue_lists_the_installed_connectors(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        page = (await admin.get("/connections")).text
        assert "Messagerie" in page and "Boîte IMAP" in page and "Lire et envoyer des mails" in page
        assert "Aucun compte connecté" in page


async def test_an_oauth_service_first_asks_for_the_households_client_with_its_guide(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        page = (await admin.get("/connectors/mailbox")).text
        assert "Créez un projet dans la console" in page
        assert RELAY in page, "the redirect URI to declare at the provider"
        assert "Connecter un compte" not in page
        await register_client(admin)
        page = (await admin.get("/connectors/mailbox")).text
        assert "Connecter un compte" in page and "client-123" in page


async def test_a_full_oauth_flow_through_the_relay(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        await register_client(admin)
        authorize = await start_flow(admin)

        sent = query(authorize)
        assert authorize.startswith("https://provider.example/authorize?")
        assert (sent["client_id"], sent["redirect_uri"], sent["scope"]) == ("client-123", RELAY, "mail.read")
        assert sent["code_challenge_method"] == "S256" and len(sent["code_challenge"]) == 43
        issued, _, instance = sent["state"].partition(".")
        padded = instance + "=" * (-len(instance) % 4)
        assert base64.urlsafe_b64decode(padded).decode() == "http://admin.test/connections/callback"
        assert len(issued) >= 32

        response = await admin.get("/connections/callback", **admin.consent(authorize))
        assert response.status_code == 303
        page = (await admin.get(response.headers["location"])).text
        assert "mathis@example.com" in page and "connectée" in page and "mailbox_search" in page
        listed = (await admin.get("/connections")).text
        assert "mathis@example.com" in listed and "Mathis" in listed
        assert admin.mail.tokens_seen, "the connector identified the account with a real token"


async def test_over_https_the_provider_comes_back_to_the_admin_directly(tmp_path: Path) -> None:
    async with Harness(tmp_path, public_url="https://nestor.example.org") as admin:
        await admin.login()
        await register_client(admin)
        authorize = await start_flow(admin, person="")
        sent = query(authorize)
        assert sent["redirect_uri"] == "https://nestor.example.org/connections/callback"
        assert "." not in sent["state"]
        response = await admin.get("/connections/callback", **admin.consent(authorize))
        connection_id = shown(response)
        assert admin.nestor.connections and admin.nestor.connections.connections[connection_id].owner is None
        assert "compte de Tout le foyer" in (await admin.get(f"/connections/{connection_id}")).text


async def test_connecting_without_a_client_or_for_a_stranger_is_refused(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        await admin.get("/connectors/mailbox")
        no_client = await admin.post("/connectors/mailbox/connect", {"person": "mathis"})
        assert no_client.status_code == 400 and "Enregistrez d" in no_client.text
        stranger = await admin.post("/connectors/mailbox/connect", {"person": "intruder"})
        assert stranger.status_code == 400 and "Personne inconnue" in stranger.text
        empty = await admin.post("/connectors/mailbox/client", {"client_id": "client-123", "client_secret": " "})
        assert empty.status_code == 400 and "Indiquez" in empty.text
        assert admin.nestor.connections and not await admin.nestor.connections.has_client("mailbox")
        not_oauth = await admin.post("/connectors/imap/client", {"client_id": "a", "client_secret": "b"})
        assert not_oauth.status_code == 400


async def test_a_secret_based_service_connects_through_its_form(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        page = (await admin.get("/connectors/imap")).text
        assert 'type="password"' in page and "Serveur" in page and "client OAuth" not in page

        missing = await admin.post("/connectors/imap/connect", {"person": "mathilde", "server": "imap.free.fr"})
        assert missing.status_code == 400 and "Champs manquants : Mot de passe d&#39;application" in missing.text
        assert 'value="imap.free.fr"' in missing.text, "what was typed is kept, except passwords"

        response = await admin.post(
            "/connectors/imap/connect", {"person": "mathilde", "server": "imap.free.fr", "password": "app-pass-777"}
        )
        connection_id = response.headers["location"].rsplit("/", 1)[1]
        assert admin.nestor.connections
        vault = admin.nestor.connections.vault
        assert await vault.get(connection_id, "secrets") == {"server": "imap.free.fr", "password": "app-pass-777"}
        assert "mathilde@free.fr" in (await admin.get(f"/connections/{connection_id}")).text
        assert not any("app-pass-777" in page for page in admin.pages)


async def test_a_secret_based_service_refusing_the_credentials_is_reported(tmp_path: Path) -> None:
    from nestor.core import ProviderError

    async with Harness(tmp_path) as admin:
        await admin.login()

        async def refuse(access: object) -> str:
            raise ProviderError("imap", "authentication failed", transient=False)

        admin.imap.identify = refuse  # ty: ignore[invalid-assignment]
        await admin.get("/connectors/imap")
        response = await admin.post("/connectors/imap/connect", {"server": "imap.free.fr", "password": "wrong"})
        assert response.status_code == 502 and "authentication failed" in response.text
        assert admin.nestor.connections and admin.nestor.connections.connections == {}


async def test_tool_settings_change_what_the_agent_sees(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        connection_id = await connect_mailbox(admin)
        assert admin.nestor.connections
        tools = ConnectorTools(admin.nestor.connections)
        assert {"mailbox_search", "mailbox_send"} <= {s.name for s in admin.nestor.agent.toolbox.specs()}

        await admin.get(f"/connections/{connection_id}")
        response = await admin.post(f"/connections/{connection_id}/tools", {"enabled": ["mailbox_search"]})
        assert response.headers["location"] == f"/connections/{connection_id}"

        assert [t.name for t in tools.tools()] == ["mailbox_search"]
        assert "mailbox_send" not in {s.name for s in admin.nestor.agent.toolbox.specs()}
        connection = admin.nestor.connections.connections[connection_id]
        assert connection.confirm_writes is False
        page = (await admin.get(f"/connections/{connection_id}")).text
        assert 'value="mailbox_send">' in page and 'value="mailbox_search" checked>' in page

        await admin.post(
            f"/connections/{connection_id}/tools",
            {"enabled": ["mailbox_search", "mailbox_send"], "confirm_writes": "on"},
        )
        assert {t.name for t in tools.tools()} == {"mailbox_search", "mailbox_send"}
        assert admin.nestor.connections.connections[connection_id].confirm_writes is True


async def test_disconnecting_needs_confirmation_then_revokes_and_forgets(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        connection_id = await connect_mailbox(admin)
        assert admin.nestor.connections
        refresh = (await admin.nestor.connections.vault.get(connection_id, "tokens") or {})["refresh_token"]

        await admin.get(f"/connections/{connection_id}")
        unconfirmed = await admin.post(f"/connections/{connection_id}/disconnect")
        assert unconfirmed.status_code == 400 and connection_id in admin.nestor.connections.connections

        response = await admin.post(f"/connections/{connection_id}/disconnect", {"confirm": "yes"})
        assert response.headers["location"] == "/connections"
        assert admin.provider.revoked == [refresh]
        assert connection_id not in admin.nestor.connections.connections
        assert await admin.nestor.connections.vault.get(connection_id, "tokens") is None
        assert "déconnecté" in (await admin.get("/connections")).text
        assert (await admin.get(f"/connections/{connection_id}")).status_code == 404


async def test_a_connection_needing_reauthorisation_is_reconnected_with_its_settings(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        old_id = await connect_mailbox(admin)
        connections = admin.nestor.connections
        assert connections
        await connections.configure(old_id, disabled_tools=["mailbox_send"])
        tokens = await connections.vault.get(old_id, "tokens") or {}
        await connections.vault.put(old_id, "tokens", {**tokens, "expires_at": "2000-01-01T00:00:00+00:00"})
        admin.provider.refusing = True
        with pytest.raises(Exception, match="invalid_grant"):
            await connections.access(connections.connections[old_id]).token()
        admin.provider.refusing = False

        page = (await admin.get(f"/connections/{old_id}")).text
        assert "à réautoriser" in page and f"/connectors/mailbox?replaces={old_id}" in page
        assert "Reconnexion" in (await admin.get("/connectors/mailbox", replaces=old_id)).text
        authorize = await start_flow(admin, replaces=old_id)
        assert old_id in connections.connections, "the broken connection stays until the new one works"
        revoked_before = list(admin.provider.revoked)
        response = await admin.get("/connections/callback", **admin.consent(authorize))
        new_id = shown(response)

        assert list(connections.connections) == [new_id]
        assert connections.connections[new_id].status is Status.CONNECTED
        assert connections.connections[new_id].disabled_tools == frozenset({"mailbox_send"})
        assert admin.provider.revoked == revoked_before, "revoking the old token could revoke the new grant"


async def test_a_refused_reconnection_keeps_the_broken_connection(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        old_id = await connect_mailbox(admin)
        connections = admin.nestor.connections
        assert connections
        await connections._mark(connections.connections[old_id], Status.NEEDS_REAUTH, "refresh refused")
        authorize = await start_flow(admin, replaces=old_id)
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize).query))["state"]
        await admin.get("/connections/callback", state=state, error="access_denied")
        assert list(connections.connections) == [old_id]


async def test_a_secret_service_is_reconnected_in_place(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        connections = admin.nestor.connections
        assert connections
        old = await connections.connect("imap", None, {"server": "imap.free.fr", "password": "old"})
        await connections.configure(old.id, confirm_writes=False)
        await connections._mark(connections.connections[old.id], Status.ERROR, "login refused")

        await admin.get("/connectors/imap", replaces=old.id)
        response = await admin.post(
            "/connectors/imap/connect", {"replaces": old.id, "server": "imap.free.fr", "password": "new"}
        )
        new_id = response.headers["location"].rsplit("/", 1)[1]
        assert list(connections.connections) == [new_id]
        assert connections.connections[new_id].confirm_writes is False


async def test_no_secret_is_ever_rendered(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        connection_id = await connect_mailbox(admin)
        for path in ("/connections", "/connectors/mailbox", f"/connections/{connection_id}", "/journal", "/people"):
            await admin.get(path)
        assert admin.nestor.connections
        tokens = await admin.nestor.connections.vault.get(connection_id, "tokens") or {}
        secrets = [CLIENT_SECRET, tokens["access_token"], tokens["refresh_token"]]
        for page in admin.pages:
            for secret in secrets:
                assert secret not in page


async def test_unknown_connectors_and_connections_are_not_found(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        assert (await admin.get("/connectors/slack")).status_code == 404
        assert (await admin.get("/connections/nope")).status_code == 404


async def test_without_connectors_the_catalogue_says_so(tmp_path: Path) -> None:
    async with Harness(tmp_path, connectors=False) as admin:
        await admin.login()
        assert "Aucun connecteur" in (await admin.get("/connections")).text
        assert (await admin.get("/connectors/mailbox")).status_code == 404


async def test_a_broken_connector_or_vault_shows_an_error_page_not_a_crash(tmp_path: Path) -> None:
    from nestor.core import ContractError, ProviderError

    async with Harness(tmp_path) as admin:
        await admin.login()
        connection_id = await connect_mailbox(admin)
        connections = admin.nestor.connections
        assert connections

        def broken(*args: object) -> list[object]:
            raise ProviderError("mailbox", "API changed", transient=False)

        admin.mail.tools = broken  # ty: ignore[invalid-assignment]
        page = await admin.get(f"/connections/{connection_id}")
        assert page.status_code == 502 and "Service indisponible" in page.text and "API changed" in page.text

        async def unreadable(owner: str, name: str) -> None:
            raise ContractError("secret 'client' cannot be opened: NESTOR_SECRET_KEY changed since it was stored")

        connections.vault.get = unreadable  # ty: ignore[invalid-assignment]
        page = await admin.get("/connectors/mailbox")
        assert page.status_code == 400 and "NESTOR_SECRET_KEY changed" in page.text


async def test_a_form_address_opened_as_a_page_is_refused_politely(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        response = await admin.post("/journal")
        assert response.status_code == 405 and "ne s&#39;utilise pas ainsi" in response.text


async def test_an_account_of_someone_no_longer_in_the_household_is_still_listed(tmp_path: Path) -> None:
    from nestor.core import PersonId

    async with Harness(tmp_path) as admin:
        await admin.login()
        assert admin.nestor.connections
        await admin.nestor.connections.connect("imap", PersonId("ancien"), {"server": "s", "password": "p"})
        assert "<td>ancien</td>" in (await admin.get("/connections")).text


@pytest.mark.parametrize(
    ("base", "direct"),
    [
        ("https://nestor.example", True),
        ("http://localhost:8080", True),
        ("http://127.0.0.1:8080", True),
        ("http://[::1]:8080", True),
        ("http://192.168.1.20:8080", False),
        ("http://nestor.local:8080", False),
    ],
)
def test_the_provider_comes_back_directly_only_over_https_or_to_this_machine(base: str, direct: bool) -> None:
    from nestor.admin.settings import CALLBACK_PATH, DEFAULT_RELAY, AdminSettings

    settings = AdminSettings()
    assert settings.redirect_uri(base) == (f"{base}{CALLBACK_PATH}" if direct else DEFAULT_RELAY)
