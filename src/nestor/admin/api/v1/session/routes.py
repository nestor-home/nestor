"""Signing in and out, who is signed in, and changing one's own password."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.passwords import checked_password
from nestor.admin.api.v1.security import Caller, same_origin, signed_in
from nestor.admin.api.v1.session.schemas import LocaleIn, LoginIn, MeOut, PasswordChangeIn
from nestor.admin.state import state

router = APIRouter(tags=["session"])
SignedIn = Annotated[Caller, Depends(signed_in)]


@router.post("/session", status_code=200, dependencies=[Depends(same_origin)])
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
    return MeOut.of(admin, account, admin.cookie.open(response, account.id, secure=admin.secure(request)))


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
    return MeOut.of(state(request), caller.account, caller.session)


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
    return MeOut.of(admin, account, caller.session)
