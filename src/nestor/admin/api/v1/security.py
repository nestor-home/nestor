"""Who calls the API, and whether they may.

A browser signs in with an account: its session cookie is HttpOnly and SameSite=Strict, and every
unsafe request also carries the session's CSRF token (given by `GET /api/v1/me`) in `X-CSRF-Token`.
The local command line uses the bearer token of `admin.token` instead, on the routes that accept it
(satellite pairing); it never needs a CSRF token since a browser cannot send it. Unsafe requests with
a body must be JSON: an HTML form from another site can send neither JSON nor custom headers.
"""

import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request

from nestor.admin.api.v1.errors import FORBIDDEN, ApiError
from nestor.admin.auth import Session
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Account, Principal, Scope

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "X-CSRF-Token"
LOCAL = Principal(scopes=frozenset({Scope.SATELLITES_MANAGE}))  # the command line on this machine

UNAUTHENTICATED = ApiError(401, "unauthenticated", "Connectez-vous pour continuer.")


@dataclass(frozen=True, slots=True)
class Caller:
    principal: Principal
    account: Account | None = None  # None for the command line
    session: Session | None = None

    @property
    def person(self) -> PersonId | None:
        return self.principal.person

    @property
    def account_id(self) -> str | None:
        return self.principal.account_id


async def json_only(request: Request) -> None:
    """Applied to the whole API: an unsafe request with a body must declare it as JSON."""
    if request.method not in UNSAFE:
        return
    has_body = request.headers.get("content-length", "0") != "0" or "transfer-encoding" in request.headers
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if has_body and media != "application/json":
        raise ApiError(415, "unsupported_media_type", "Le corps de la requête doit être du JSON.")


async def signed_in(request: Request) -> Caller:
    admin = state(request)
    session = admin.cookie.read(request)
    account = admin.accounts.accounts.get(session.account_id or "") if session else None
    if session is None or account is None or account.disabled:
        raise UNAUTHENTICATED
    if request.method in UNSAFE:
        given = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(given.encode(), session.csrf.encode()):
            raise ApiError(403, "csrf_failed", "Requête refusée : rechargez la page et recommencez.")
    return Caller(account.principal(), account, session)


async def signed_in_or_local(request: Request) -> Caller:
    authorization = request.headers.get("authorization")
    if authorization is None:
        return await signed_in(request)
    expected = state(request).api_token
    scheme, _, given = authorization.partition(" ")
    if expected is None or scheme.lower() != "bearer" or not hmac.compare_digest(given.strip(), expected):
        raise ApiError(
            401, "unauthenticated", "Jeton d'administration absent ou faux.", headers={"WWW-Authenticate": "Bearer"}
        )
    return Caller(LOCAL)


def allowed(*scopes: Scope, local: bool = False) -> Callable[[Request], Awaitable[Caller]]:
    """A dependency: the caller, when they hold any of `scopes` (the route then narrows to what they reach)."""

    async def caller(request: Request) -> Caller:
        found = await (signed_in_or_local if local else signed_in)(request)
        if not any(found.principal.can(scope) for scope in scopes):
            raise ApiError(403, "forbidden", FORBIDDEN)
        return found

    return caller
