"""How a remote MCP server is authorised, asked the way the MCP authorization spec says, with the SDK's own steps.

A request without credentials is refused with a 401 by a server that wants them. Its protected resource metadata
(RFC 9728, found from the `WWW-Authenticate` header or the well-known paths) names its authorization server, whose
metadata (RFC 8414, or OpenID Connect discovery) gives the endpoints; servers of the 2025-03-26 era publish it at
their own origin. When that server allows it, a client is registered for Nestor on the spot (RFC 7591), sending
people back to the admin. The SDK builds and reads every one of these requests; what it does not fit is its client
provider, which waits for the person's consent inside one HTTP request, where the admin needs two.
"""

import urllib.parse
from collections.abc import Mapping

import httpx2
from mcp.client.auth import OAuthFlowError, OAuthRegistrationError
from mcp.client.auth.oauth2 import check_registration_usable
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    extract_resource_metadata_from_www_auth,
    extract_scope_from_www_auth,
    get_client_metadata_scopes,
    handle_auth_metadata_response,
    handle_protected_resource_response,
    handle_registration_response,
    issuers_match,
)
from mcp.shared.auth import (
    DEFAULT_GRANT_TYPES,
    OAuthClientMetadata,
    OAuthMetadata,
    ProtectedResourceMetadata,
    TokenEndpointAuthMethod,
)
from mcp.shared.auth_utils import check_resource_allowed, resource_url_from_server_url
from mcp_types import LATEST_PROTOCOL_VERSION
from pydantic import AnyHttpUrl, AnyUrl

from nestor import __version__
from nestor.core import ProviderError
from nestor.core.i18n import Message
from nestor.modules.connectors import Discovery, OAuthSpec

PROVIDER = "mcp"
# What an MCP client sends first; a server that wants credentials refuses it with a 401.
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": LATEST_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "nestor", "version": __version__},
    },
}
# Client authentications Nestor can do at a token endpoint, the one it prefers first (RFC 8414's default last).
UNAVAILABLE, ELSEWHERE, METHODS = (
    "connector-mcp-metadata-unavailable",
    "connector-mcp-metadata-elsewhere",
    "connector-mcp-auth-methods",
)
AUTH_METHODS: tuple[TokenEndpointAuthMethod, ...] = ("client_secret_post", "client_secret_basic", "none")


async def discover(url: str, redirect_uri: str, typed: Mapping[str, str], http: httpx2.AsyncClient) -> Discovery:
    """How the server at `url` is authorised; `typed` is the OAuth client the person gave (`client_id`,
    `client_secret`), used instead of registering one. `ProviderError` when it cannot be reached or its metadata is
    wrong."""
    try:
        return await _discover(url, redirect_uri, typed, http)
    except (OAuthFlowError, OAuthRegistrationError) as error:
        raise _refused(str(error), "connector-mcp-authorization", transient=False) from None
    except httpx2.HTTPError as error:
        raise _refused(f"unreachable ({type(error).__name__})", "mcp-unreachable", transient=True, server=url) from None


async def _discover(url: str, redirect_uri: str, typed: Mapping[str, str], http: httpx2.AsyncClient) -> Discovery:
    probe = await http.post(url, json=INITIALIZE, headers={"Accept": "application/json, text/event-stream"})
    if probe.status_code != 401:
        return Discovery()  # it answers without credentials, or says what is wrong when connected
    protected = await _protected_resource(url, probe, http)
    resource = _resource(url, protected)
    issuer = str(protected.authorization_servers[0]) if protected else None
    metadata = await _authorization_server(url, issuer, http)
    if metadata is None:
        return Discovery()  # refused without saying where to authorise: it takes a token
    scope = get_client_metadata_scopes(extract_scope_from_www_auth(probe), protected, metadata, DEFAULT_GRANT_TYPES)
    scopes = tuple(scope.split()) if scope else ()
    spec = OAuthSpec(
        authorize_url=str(metadata.authorization_endpoint),
        token_url=str(metadata.token_endpoint),
        revoke_url=str(metadata.revocation_endpoint) if metadata.revocation_endpoint else None,
        scopes=scopes,
        # OpenID Connect issues a refresh token for offline access only after an explicit consent
        extra_authorize={"prompt": "consent"} if "offline_access" in scopes else {},
        resource=resource,
    )
    if typed.get("client_id"):
        return Discovery(oauth=spec, client=dict(typed))
    if metadata.registration_endpoint is None:
        return Discovery(oauth=spec)
    return Discovery(oauth=spec, client=await _register(url, redirect_uri, scope, metadata, http))


async def _protected_resource(
    url: str, probe: httpx2.Response, http: httpx2.AsyncClient
) -> ProtectedResourceMetadata | None:
    for candidate in build_protected_resource_metadata_discovery_urls(
        extract_resource_metadata_from_www_auth(probe), url
    ):
        response = await http.send(create_oauth_metadata_request(candidate))
        if response.status_code >= 500 or response.status_code == 429:
            raise _refused(f"its metadata answered HTTP {response.status_code}", UNAVAILABLE, transient=True)
        if (found := await handle_protected_resource_response(response)) is not None:
            return found
    return None


async def _authorization_server(url: str, issuer: str | None, http: httpx2.AsyncClient) -> OAuthMetadata | None:
    expected = issuer or _origin(url)
    for candidate in build_oauth_authorization_server_metadata_discovery_urls(issuer, url):
        served, found = await handle_auth_metadata_response(await http.send(create_oauth_metadata_request(candidate)))
        if not served:
            raise _refused("its authorization server's metadata is unavailable", UNAVAILABLE, transient=True)
        if found is not None:
            if not issuers_match(str(found.issuer), expected):  # RFC 8414 §3.3: another server's metadata
                raise _refused(
                    f"the metadata of {expected} names {found.issuer}",
                    ELSEWHERE,
                    transient=False,
                    named=str(found.issuer),
                )
            return found
    return None


def _resource(url: str, protected: ProtectedResourceMetadata | None) -> str:
    """RFC 8707: the server's canonical address, or the resource its metadata names when that one contains it."""
    resource = resource_url_from_server_url(url)
    if protected is None:
        return resource
    named = str(protected.resource)
    if not check_resource_allowed(requested_resource=resource, configured_resource=named):
        raise _refused(f"its metadata is for {named}, not {resource}", ELSEWHERE, transient=False, named=named)
    return named


async def _register(
    url: str, redirect_uri: str, scope: str | None, metadata: OAuthMetadata, http: httpx2.AsyncClient
) -> dict[str, str]:
    offered = metadata.token_endpoint_auth_methods_supported or ["client_secret_basic"]
    method = next((m for m in AUTH_METHODS if m in offered), None)
    if method is None:
        methods = ", ".join(offered)
        raise _refused(f"its authorization server only takes {methods}", METHODS, transient=False, methods=methods)
    request = OAuthClientMetadata(
        redirect_uris=[AnyUrl(redirect_uri)],
        token_endpoint_auth_method=method,
        grant_types=list(DEFAULT_GRANT_TYPES),
        response_types=["code"],
        scope=scope,
        client_name="Nestor",
        client_uri=AnyHttpUrl("https://nestorhome.dev"),
        software_id="nestor",
        software_version=__version__,
        application_type="web",
    )
    registered = await handle_registration_response(
        await http.send(create_client_registration_request(metadata, request, _origin(url)))
    )
    check_registration_usable(registered)
    client = {"client_id": registered.client_id}
    if registered.client_secret:
        client["client_secret"] = registered.client_secret
    if registered.token_endpoint_auth_method:
        client["token_endpoint_auth_method"] = registered.token_endpoint_auth_method
    return client


def _refused(message: str, reason: str, *, transient: bool, **args: str) -> ProviderError:
    return ProviderError(PROVIDER, message, transient=transient, reason=Message(reason, args))


def _origin(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
