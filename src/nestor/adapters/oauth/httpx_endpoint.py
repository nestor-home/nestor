"""OAuth 2 token requests over HTTP: authorization code with PKCE, refresh (RFC 6749), revocation (RFC 7009).

The client authenticates with `client_secret_post` (credentials in the form body), which every
mainstream provider accepts. Nothing sent or received is logged: only the host and the status code.
"""

import logging
import urllib.parse
from datetime import timedelta

import httpx

from nestor.core import ProviderError, utc_now
from nestor.modules.connectors import OAuthSpec, Secrets, TokenEndpoint, Tokens

log = logging.getLogger(__name__)

# Errors that retrying cannot fix: the grant or the client is wrong, the person must act.
PERMANENT = frozenset(
    {
        "invalid_grant",
        "invalid_client",
        "unauthorized_client",
        "invalid_request",
        "unsupported_grant_type",
        "invalid_scope",
        "access_denied",
    }
)


class HttpxTokenEndpoint(TokenEndpoint):
    name = "oauth-token-endpoint"

    def __init__(self, *, timeout_s: float = 15.0, client: httpx.AsyncClient | None = None) -> None:
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def exchange(self, spec: OAuthSpec, client: Secrets, code: str, verifier: str, redirect_uri: str) -> Tokens:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        return _tokens(await self._post(spec.token_url, form, client), spec.token_url)

    async def refresh(self, spec: OAuthSpec, client: Secrets, refresh_token: str) -> Tokens:
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        return _tokens(await self._post(spec.token_url, form, client), spec.token_url)

    async def revoke(self, spec: OAuthSpec, client: Secrets, token: str) -> None:
        if spec.revoke_url is None:
            return
        try:
            await self._post(spec.revoke_url, {"token": token}, client)
        except ProviderError as error:
            if "invalid_token" not in str(error):  # already revoked or expired: what we wanted
                raise

    async def _post(self, url: str, form: dict[str, str], client: Secrets) -> dict[str, object]:
        provider = _host(url)
        body = {**form, "client_id": client["client_id"]}
        if client.get("client_secret"):
            body["client_secret"] = client["client_secret"]
        if self._client is None:
            await self.start()
        assert self._client is not None
        try:
            response = await self._client.post(
                url, data=body, headers={"Accept": "application/json"}, timeout=self._timeout_s
            )
        except httpx.TimeoutException:
            raise ProviderError(provider, "token endpoint timed out", transient=True) from None
        except httpx.HTTPError as error:
            raise ProviderError(
                provider, f"token endpoint unreachable ({type(error).__name__})", transient=True
            ) from None
        log.debug("oauth %s: HTTP %s", provider, response.status_code)
        payload = _json(response)
        error = payload.get("error")
        if response.status_code >= 500 or response.status_code == 429:
            raise ProviderError(provider, f"HTTP {response.status_code}", transient=True)
        if error or response.status_code >= 400:
            code = str(error or f"HTTP {response.status_code}")
            raise ProviderError(provider, code, transient=code not in PERMANENT and response.status_code < 400)
        return payload


def _tokens(payload: dict[str, object], url: str) -> Tokens:
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise ProviderError(_host(url), "the token response has no access_token", transient=False)
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    scope = payload.get("scope")
    try:
        lifetime = float(expires_in) if isinstance(expires_in, int | float | str) else None
    except ValueError:
        lifetime = None
    return Tokens(
        access_token=access,
        refresh_token=refresh if isinstance(refresh, str) and refresh else None,
        expires_at=utc_now() + timedelta(seconds=lifetime) if lifetime is not None else None,
        scopes=tuple(scope.split()) if isinstance(scope, str) else (),
    )


def _json(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or url
