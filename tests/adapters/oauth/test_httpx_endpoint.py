"""The HTTP token endpoint against a mocked provider: what it sends, what it understands, how it fails."""

import logging
import urllib.parse

import httpx
import pytest
import respx

from nestor.adapters.oauth import HttpxTokenEndpoint
from nestor.core import ProviderError, utc_now
from nestor.modules.connectors import OAuthSpec

SPEC = OAuthSpec(
    authorize_url="https://accounts.test/authorize",
    token_url="https://accounts.test/token",
    revoke_url="https://accounts.test/revoke",
    scopes=("mail.read",),
)
CLIENT = {"client_id": "client-123", "client_secret": "client-secret-xyz"}


def form(request: httpx.Request) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(request.content.decode()))


@respx.mock
async def test_a_code_is_exchanged_with_its_pkce_verifier_and_the_client_in_the_body() -> None:
    route = respx.post(SPEC.token_url).respond(
        200,
        json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "scope": "mail.read openid"},
    )
    async with HttpxTokenEndpoint() as endpoint:
        tokens = await endpoint.exchange(SPEC, CLIENT, "the-code", "the-verifier", "https://relay.test/oauth")

    sent = form(route.calls.last.request)
    assert sent == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "redirect_uri": "https://relay.test/oauth",
        "code_verifier": "the-verifier",
        "client_id": "client-123",
        "client_secret": "client-secret-xyz",
    }
    assert (tokens.access_token, tokens.refresh_token, tokens.scopes) == ("at-1", "rt-1", ("mail.read", "openid"))
    assert tokens.expires_at is not None and 3500 < (tokens.expires_at - utc_now()).total_seconds() <= 3600


@respx.mock
async def test_a_refresh_without_new_refresh_token_or_expiry_is_understood() -> None:
    route = respx.post(SPEC.token_url).respond(200, json={"access_token": "at-2", "expires_in": "soon"})
    endpoint = HttpxTokenEndpoint()  # used without being started: it opens its client on first use
    tokens = await endpoint.refresh(SPEC, {"client_id": "public-client"}, "rt-1")
    await endpoint.close()

    assert form(route.calls.last.request) == {
        "grant_type": "refresh_token",
        "refresh_token": "rt-1",
        "client_id": "public-client",
    }
    assert (tokens.refresh_token, tokens.expires_at, tokens.scopes) == (None, None, ())


@pytest.mark.parametrize("error", ["invalid_grant", "invalid_client", "unauthorized_client"])
@respx.mock
async def test_a_refused_grant_is_permanent_so_the_person_reconnects(error: str) -> None:
    respx.post(SPEC.token_url).respond(400, json={"error": error, "error_description": "Token has been revoked."})
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError, match=error) as raised:
            await endpoint.refresh(SPEC, CLIENT, "rt-1")
    assert raised.value.transient is False and raised.value.provider == "accounts.test"


@respx.mock
async def test_an_error_in_a_successful_response_is_still_an_error() -> None:
    respx.post(SPEC.token_url).respond(200, json={"error": "bad_verification_code"})
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError, match="bad_verification_code") as raised:
            await endpoint.exchange(SPEC, CLIENT, "c", "v", "https://x.test/cb")
    assert raised.value.transient is True


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503, text="down"), httpx.Response(429, json={"error": "rate_limited"})],
)
@respx.mock
async def test_an_outage_or_a_rate_limit_is_transient(response: httpx.Response) -> None:
    respx.post(SPEC.token_url).mock(return_value=response)
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError) as raised:
            await endpoint.refresh(SPEC, CLIENT, "rt-1")
    assert raised.value.transient is True


@pytest.mark.parametrize(
    ("failure", "message"),
    [(httpx.ReadTimeout("slow"), "timed out"), (httpx.ConnectError("refused"), "unreachable")],
)
@respx.mock
async def test_a_network_failure_is_transient(failure: Exception, message: str) -> None:
    respx.post(SPEC.token_url).mock(side_effect=failure)
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError, match=message) as raised:
            await endpoint.refresh(SPEC, CLIENT, "rt-1")
    assert raised.value.transient is True


@respx.mock
async def test_a_response_without_access_token_is_refused() -> None:
    respx.post(SPEC.token_url).respond(200, text="<html>login</html>")
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError, match="no access_token") as raised:
            await endpoint.exchange(SPEC, CLIENT, "c", "v", "https://x.test/cb")
    assert raised.value.transient is False


@respx.mock
async def test_a_refused_client_on_a_4xx_without_body_is_permanent() -> None:
    respx.post(SPEC.token_url).respond(401, json=["unexpected"])
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError, match="HTTP 401") as raised:
            await endpoint.refresh(SPEC, CLIENT, "rt-1")
    assert raised.value.transient is False


@respx.mock
async def test_revocation_sends_the_token_and_accepts_an_already_dead_one() -> None:
    route = respx.post(SPEC.revoke_url).mock(
        side_effect=[httpx.Response(200), httpx.Response(400, json={"error": "invalid_token"})]
    )
    async with HttpxTokenEndpoint() as endpoint:
        await endpoint.revoke(SPEC, CLIENT, "rt-1")
        await endpoint.revoke(SPEC, CLIENT, "rt-1")
    assert form(route.calls[0].request)["token"] == "rt-1" and route.call_count == 2


@respx.mock
async def test_a_failed_revocation_is_reported() -> None:
    respx.post(SPEC.revoke_url).respond(503)
    async with HttpxTokenEndpoint() as endpoint:
        with pytest.raises(ProviderError):
            await endpoint.revoke(SPEC, CLIENT, "rt-1")


@respx.mock
async def test_a_provider_without_revocation_is_not_called() -> None:
    async with HttpxTokenEndpoint() as endpoint:
        await endpoint.revoke(OAuthSpec(authorize_url="a", token_url=SPEC.token_url, scopes=()), CLIENT, "rt-1")
    assert respx.calls.call_count == 0


@respx.mock
async def test_nothing_secret_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    respx.post(SPEC.token_url).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "at-secret-1", "refresh_token": "rt-secret-1"}),
            httpx.Response(400, json={"error": "invalid_grant"}),
        ]
    )
    caplog.set_level(logging.DEBUG)
    async with HttpxTokenEndpoint() as endpoint:
        await endpoint.exchange(SPEC, CLIENT, "code-secret", "verifier-secret", "https://x.test/cb")
        with pytest.raises(ProviderError):
            await endpoint.refresh(SPEC, CLIENT, "rt-secret-1")
    for secret in ("at-secret-1", "rt-secret-1", "code-secret", "verifier-secret", "client-secret-xyz"):
        assert secret not in caplog.text


@respx.mock
async def test_a_shared_http_client_is_used_and_left_open() -> None:
    respx.post(SPEC.token_url).respond(200, json={"access_token": "at"})
    async with httpx.AsyncClient() as client:
        async with HttpxTokenEndpoint(client=client) as endpoint:
            await endpoint.refresh(SPEC, CLIENT, "rt")
        assert not client.is_closed
