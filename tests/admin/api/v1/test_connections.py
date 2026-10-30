"""Connecting services through the API: the household's OAuth client, consent end to end with a fake
provider, the callback and its failures, tools, reconnecting, secrets typed once, members' own accounts."""

import base64
import urllib.parse
from pathlib import Path

import pytest

from nestor.core import PersonId, ProviderError
from nestor.modules.accounts import Role
from nestor.modules.connectors import ConnectorTools, Status
from nestor.modules.connectors import service as connections_service

from ...harness import CLIENT_SECRET, Api, Harness

RELAY = "https://nestor.mathislambert.fr/redirect/oauth"


def query(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


async def register(api: Api) -> dict:
    response = await api.put(
        "/api/v1/connectors/mailbox/client", {"client_id": "client-123", "client_secret": CLIENT_SECRET}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def begin(api: Api, **body: str) -> str:
    response = await api.post("/api/v1/connectors/mailbox/authorizations", body)
    assert response.status_code == 200, response.text
    return response.json()["authorize_url"]


async def connect(admin: Harness, api: Api, **body: str) -> str:
    response = await admin.come_back(**admin.consent(await begin(api, **body)))
    assert response.status_code == 303
    location = urllib.parse.urlsplit(response.headers["location"])
    assert location.query == "connected=1"
    return location.path.rsplit("/", 1)[1]


async def test_the_catalogue_says_how_to_connect_each_service(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        catalogue = {c["kind"]: c for c in (await api.get("/api/v1/connectors")).json()}
        mailbox, imap = catalogue["mailbox"], catalogue["imap"]
        assert mailbox["title"] == "Messagerie" and "Créez un projet" in mailbox["setup"]
        assert mailbox["oauth"] == {"registered": False, "client_id": None, "redirect_uri": RELAY, "relayed": True}
        assert imap["oauth"] is None and imap["auth_label"] == "identifiants"
        assert {"name": "server", "label": "Serveur", "secret": False, "default": None} in imap["fields"]
        registered = await register(api)
        assert registered["oauth"]["registered"] and registered["oauth"]["client_id"] == "client-123"
        assert (await api.get("/api/v1/connectors/slack")).status_code == 404


async def test_a_full_oauth_flow_through_the_relay(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        authorize = await begin(api, person="mathis")
        sent = query(authorize)
        assert authorize.startswith("https://provider.example/authorize?")
        assert (sent["client_id"], sent["redirect_uri"], sent["scope"]) == ("client-123", RELAY, "mail.read")
        assert sent["code_challenge_method"] == "S256" and len(sent["code_challenge"]) == 43
        issued, _, instance = sent["state"].partition(".")
        assert base64.urlsafe_b64decode(instance + "=" * (-len(instance) % 4)).decode() == (
            "http://admin.test/connections/callback"
        )
        assert len(issued) >= 32

        response = await admin.come_back(**admin.consent(authorize))
        connection_id = urllib.parse.urlsplit(response.headers["location"]).path.rsplit("/", 1)[1]
        detail = (await api.get(f"/api/v1/connections/{connection_id}")).json()
        assert detail["account"] == "mathis@example.com" and detail["status_label"] == "connectée"
        assert detail["owner"] == {"id": "mathis", "name": "Mathis"}
        assert {t["name"]: t["risk"] for t in detail["tools"]} == {
            "mailbox_search": "read",
            "mailbox_send": "sensitive",
        }
        assert [c["id"] for c in (await api.get("/api/v1/connections")).json()] == [connection_id]
        assert admin.mail.tokens_seen, "the connector identified the account with a real token"


async def test_over_https_the_provider_comes_back_directly_for_the_whole_household(tmp_path: Path) -> None:
    async with Harness(tmp_path, public_url="https://nestor.example.org") as admin:
        api = await admin.api()
        await register(api)
        authorize = await begin(api)
        assert query(authorize)["redirect_uri"] == "https://nestor.example.org/connections/callback"
        assert "." not in query(authorize)["state"]
        connection_id = await connect(admin, api)
        assert (await api.get(f"/api/v1/connections/{connection_id}")).json()["owner"] is None


@pytest.mark.parametrize(
    ("returned", "code"),
    [
        ({"error": "access_denied"}, "access_denied"),
        ({"error": "server_error"}, "provider_error"),
        ({"code": "forged-code"}, "exchange_failed"),
    ],
)
async def test_a_failed_return_connects_nothing_and_says_why(tmp_path: Path, returned: dict, code: str) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        state = query(await begin(api))["state"]
        response = await admin.come_back(state=state, **returned)
        assert response.headers["location"] == f"/connections?oauth_error={code}"
        assert admin.nestor.connections and admin.nestor.connections.connections == {}
        late = await admin.come_back(state=state, code="late")
        assert late.headers["location"] == "/connections?oauth_error=unknown_flow", "a state is used once"


async def test_an_expired_authorisation_request_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        back = admin.consent(await begin(api))
        monkeypatch.setattr(connections_service, "PENDING_TTL_S", -1.0)
        assert (await admin.come_back(**back)).headers["location"] == "/connections?oauth_error=expired"


async def test_a_flow_started_by_an_account_disabled_since_completes_nothing(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        lucie = await admin.account("lucie", Role.ADMIN, "lucie")
        api = await admin.api("lucie")
        await register(api)
        back = admin.consent(await begin(api))
        assert admin.owner
        await admin.nestor.accounts.disable(lucie.id, by=admin.owner.principal())
        assert (await admin.come_back(**back)).headers["location"] == "/connections?oauth_error=forbidden"
        assert admin.nestor.connections and admin.nestor.connections.connections == {}


async def test_connecting_needs_a_client_and_an_oauth_service(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        no_client = await api.post("/api/v1/connectors/mailbox/authorizations", {})
        assert no_client.json()["error"]["code"] == "client_missing"
        empty = await api.put("/api/v1/connectors/mailbox/client", {"client_id": "c", "client_secret": " "})
        assert empty.json()["error"]["code"] == "client_incomplete"
        not_oauth = await api.put("/api/v1/connectors/imap/client", {"client_id": "a", "client_secret": "b"})
        assert not_oauth.json()["error"]["code"] == "not_oauth"
        assert (await api.post("/api/v1/connectors/imap/authorizations", {})).json()["error"]["code"] == "not_oauth"
        assert (await api.post("/api/v1/connectors/mailbox/connections", {})).json()["error"]["code"] == "oauth"
        stranger = await api.post("/api/v1/connectors/mailbox/authorizations", {"person": "intruder"})
        assert stranger.json()["error"]["code"] == "unknown_person"


async def test_tool_settings_change_what_the_agent_sees(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        connection_id = await connect(admin, api, person="mathis")
        assert admin.nestor.connections
        tools = ConnectorTools(admin.nestor.connections)
        changed = await api.patch(
            f"/api/v1/connections/{connection_id}", {"disabled_tools": ["mailbox_send"], "confirm_writes": False}
        )
        detail = changed.json()
        assert {t["name"]: t["enabled"] for t in detail["tools"]} == {"mailbox_search": True, "mailbox_send": False}
        assert detail["confirm_writes"] is False
        assert [t.name for t in tools.tools()] == ["mailbox_search"]
        unknown = await api.patch(f"/api/v1/connections/{connection_id}", {"disabled_tools": ["rm_rf"]})
        assert unknown.json()["error"]["code"] == "unknown_tool"
        await api.patch(f"/api/v1/connections/{connection_id}", {"disabled_tools": []})
        assert {t.name for t in tools.tools()} == {"mailbox_search", "mailbox_send"}
        assert admin.nestor.connections.connections[connection_id].confirm_writes is False


async def test_disconnecting_revokes_and_forgets(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        connection_id = await connect(admin, api)
        assert admin.nestor.connections
        refresh = (await admin.nestor.connections.vault.get(connection_id, "tokens") or {})["refresh_token"]
        assert (await api.delete(f"/api/v1/connections/{connection_id}")).status_code == 204
        assert admin.provider.revoked == [refresh]
        assert await admin.nestor.connections.vault.get(connection_id, "tokens") is None
        assert (await api.get(f"/api/v1/connections/{connection_id}")).status_code == 404


async def test_a_broken_connection_is_reconnected_with_its_settings_and_kept_until_then(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        old_id = await connect(admin, api, person="mathis")
        connections = admin.nestor.connections
        assert connections
        await connections.configure(old_id, disabled_tools=["mailbox_send"])
        await connections._mark(connections.connections[old_id], Status.NEEDS_REAUTH, "refresh refused")

        refused = query(await begin(api, person="mathis", replaces=old_id))["state"]
        await admin.come_back(state=refused, error="access_denied")
        assert list(connections.connections) == [old_id], "a refused consent loses nothing"

        authorize = await begin(api, person="mathis", replaces=old_id)
        revoked_before = list(admin.provider.revoked)
        new_id = urllib.parse.urlsplit((await admin.come_back(**admin.consent(authorize))).headers["location"]).path
        new_id = new_id.rsplit("/", 1)[1]
        assert list(connections.connections) == [new_id]
        assert connections.connections[new_id].disabled_tools == frozenset({"mailbox_send"})
        assert admin.provider.revoked == revoked_before, "revoking the old token could revoke the new grant"


async def test_a_secret_based_service_connects_with_its_fields_typed_once(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        api = await admin.api("mathilde")
        missing = await api.post("/api/v1/connectors/imap/connections", {"values": {"server": "imap.free.fr"}})
        assert missing.json()["error"]["message"] == "Champs manquants : Mot de passe d'application."
        created = await api.post(
            "/api/v1/connectors/imap/connections", {"values": {"server": "imap.free.fr", "password": "app-pass-777"}}
        )
        assert created.status_code == 201
        detail = created.json()
        assert detail["account"] == "mathilde@free.fr" and detail["owner"]["id"] == "mathilde", "for oneself"
        assert admin.nestor.connections
        stored = await admin.nestor.connections.vault.get(detail["id"], "secrets")
        assert stored == {"server": "imap.free.fr", "password": "app-pass-777"}
        assert not any("app-pass-777" in seen for seen in admin.seen)

        await admin.nestor.connections._mark(admin.nestor.connections.connections[detail["id"]], Status.ERROR, "x")
        replaced = await api.post(
            "/api/v1/connectors/imap/connections",
            {"replaces": detail["id"], "values": {"server": "imap.free.fr", "password": "new"}},
        )
        assert [c["id"] for c in (await api.get("/api/v1/connections")).json()] == [replaced.json()["id"]]


async def test_credentials_the_service_refuses_are_reported(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:

        async def refuse(access: object) -> str:
            raise ProviderError("imap", "authentication failed", transient=False)

        admin.imap.identify = refuse  # ty: ignore[invalid-assignment]
        api = await admin.api()
        response = await api.post("/api/v1/connectors/imap/connections", {"values": {"server": "s", "password": "p"}})
        assert response.status_code == 502 and "authentication failed" in response.json()["error"]["message"]


async def test_a_member_reaches_only_their_own_connections(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        connections = admin.nestor.connections
        assert connections
        theirs = await connections.connect("imap", PersonId("mathilde"), {"server": "s", "password": "p"})
        mine = await connections.connect("imap", PersonId("mathis"), {"server": "s", "password": "p"})
        shared = await connections.connect("imap", None, {"server": "s", "password": "p"})
        api = await admin.api("mathilde")
        assert [c["id"] for c in (await api.get("/api/v1/connections")).json()] == [theirs.id]
        for other in (mine.id, shared.id):
            assert (await api.get(f"/api/v1/connections/{other}")).status_code == 404
            assert (await api.delete(f"/api/v1/connections/{other}")).status_code == 404
        for person in ("mathis",):
            response = await api.post("/api/v1/connectors/imap/connections", {"person": person, "values": {}})
            assert response.status_code == 403
        assert (
            await api.put("/api/v1/connectors/mailbox/client", {"client_id": "a", "client_secret": "b"})
        ).status_code == 403
        assert (
            await api.post("/api/v1/connectors/imap/connections", {"replaces": mine.id, "values": {}})
        ).status_code == 404


async def test_without_connectors_the_catalogue_says_so(tmp_path: Path) -> None:
    async with Harness(tmp_path, connectors=False) as admin:
        api = await admin.api()
        for path in ("/api/v1/connectors", "/api/v1/connections"):
            response = await api.get(path)
            assert response.status_code == 404 and response.json()["error"]["code"] == "no_connectors"
        assert (await admin.come_back(state="s", code="c")).headers[
            "location"
        ] == "/connections?oauth_error=unknown_flow"


async def test_no_secret_is_ever_returned(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        await register(api)
        connection_id = await connect(admin, api, person="mathis")
        for path in (
            "/api/v1/connectors",
            f"/api/v1/connections/{connection_id}",
            "/api/v1/journal",
            "/api/v1/household/people",
        ):
            await api.get(path)
        assert admin.nestor.connections
        tokens = await admin.nestor.connections.vault.get(connection_id, "tokens") or {}
        for seen in admin.seen:
            for secret in (CLIENT_SECRET, tokens["access_token"], tokens["refresh_token"]):
                assert secret not in seen


@pytest.mark.parametrize(
    ("public_url", "direct"),
    [
        ("https://nestor.example", True),
        ("http://localhost:8080", True),
        ("http://127.0.0.1:8080", True),
        ("http://[::1]:8080", True),
        ("http://192.168.1.20:8080", False),
        ("http://nestor.local:8080", False),
    ],
)
async def test_the_provider_comes_back_directly_only_over_https_or_to_this_machine(
    tmp_path: Path, public_url: str, direct: bool
) -> None:
    async with Harness(tmp_path, public_url=public_url) as admin:
        api = await admin.api()
        await register(api)
        sent = query(await begin(api))
        assert sent["redirect_uri"] == (f"{public_url}/connections/callback" if direct else RELAY)
        assert ("." in sent["state"]) is not direct, "only the relay needs to be told where this admin is"


async def test_the_relay_page_is_served_as_a_standalone_page(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        page = await admin.browser.get("/static/relay/oauth.html")
        assert page.status_code == 200 and "relay.js" in page.text
        assert (await admin.browser.get("/static/admin.css")).status_code != 200
