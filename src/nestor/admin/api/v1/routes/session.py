"""Signing in and out, who is signed in, and changing one's own password."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.language import account_locale
from nestor.admin.api.v1.models import AccountOut, Input, People
from nestor.admin.api.v1.passwords import checked_password
from nestor.admin.api.v1.security import Caller, signed_in
from nestor.admin.auth import Session
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState, state
from nestor.modules.accounts import Account, Scope

router = APIRouter(tags=["session"])
SignedIn = Annotated[Caller, Depends(signed_in)]


class LoginIn(Input):
    login: str
    password: str


class MeOut(BaseModel):
    account: AccountOut
    locale: str  # the language it reads in: its choice, else the household's (`account.locale` is the choice)
    scopes: list[Scope]  # what the front may offer; the API checks them again on every request
    csrf_token: str  # send it back in `X-CSRF-Token` on every POST, PUT, PATCH and DELETE
    assistant: str  # the assistant's name, for the front's header


class LocaleIn(Input):
    locale: str | None  # one of `GET /i18n` locales; None: back to the household's language


class PasswordChangeIn(Input):
    current_password: str
    new_password: str


@router.post("/session", status_code=200)
async def create_session(request: Request, response: Response, body: LoginIn) -> MeOut:
    """Sign in. Throttled per client: after 5 failures, 429 with `Retry-After` for 15 minutes."""
    admin = state(request)
    client = request.client.host if request.client else "unknown"
    if wait := admin.throttle.wait_s(client):
        minutes = max(1, round(wait / 60))
        raise ApiError(429, "throttled", headers={"Retry-After": str(round(wait))}, minutes=minutes)
    account = await admin.accounts.authenticate(body.login, body.password, client=client)
    if account is None:
        admin.throttle.failed(client)
        raise ApiError(401, "invalid_credentials")
    admin.throttle.succeeded(client)
    if previous := admin.cookie.read(request):
        admin.sessions.close(previous)
    return open_session(request, response, account)


@router.delete("/session", status_code=204)
async def delete_session(request: Request, caller: SignedIn) -> Response:
    """Sign out: this session only."""
    admin = state(request)
    if caller.session:
        admin.sessions.close(caller.session)
    response = Response(status_code=204)
    admin.cookie.clear(response)
    return response


@router.get("/me")
async def get_me(request: Request, caller: SignedIn) -> MeOut:
    assert caller.account and caller.session
    return _me(state(request), caller.account, caller.session)


@router.put("/me/password", status_code=204)
async def change_my_password(request: Request, caller: SignedIn, body: PasswordChangeIn) -> Response:
    """Change one's own password with the current one; every other session of the account is signed out."""
    admin = state(request)
    assert caller.account
    await admin.accounts.set_password(
        caller.account.id, checked_password(body.new_password), by=caller.principal, current=body.current_password
    )
    admin.sessions.revoke(caller.account.id, keep=caller.session)
    return Response(status_code=204)


@router.put("/me/locale")
async def change_my_locale(request: Request, caller: SignedIn, body: LocaleIn) -> MeOut:
    """Choose the language the admin is shown in."""
    admin = state(request)
    assert caller.account and caller.session
    available = {str(locale).casefold(): locale for locale in admin.nestor.localizer.locales}
    chosen = available.get(body.locale.casefold()) if body.locale is not None else None
    if body.locale is not None and chosen is None:
        raise ApiError(400, "unknown_locale")
    account = await admin.accounts.set_locale(caller.account.id, chosen, by=caller.principal)
    return _me(admin, account, caller.session)


def open_session(request: Request, response: Response, account: Account) -> MeOut:
    """A fresh session for `account`, its cookie on `response`."""
    admin = state(request)
    session = admin.sessions.open(account.id)
    admin.cookie.give(response, session, secure=admin.secure(request))
    return _me(admin, account, session)


def _me(admin: AdminState, account: Account, session: Session) -> MeOut:
    locale = account_locale(admin, account)
    words = Phrasebook(admin.nestor.localizer, locale)
    return MeOut(
        account=AccountOut.of(account, People(admin.nestor.household), words),
        locale=locale,
        scopes=sorted(account.principal().scopes),
        csrf_token=session.csrf,
        assistant=admin.nestor.config.persona.name,
    )
