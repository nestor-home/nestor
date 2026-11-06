"""Accounts and invitations: who may sign in, with which role. Owners are touched only by owners."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.accounts.schemas import (
    AccountOut,
    InvitationAcceptIn,
    InvitationCreated,
    InvitationIn,
    InvitationOut,
    InvitationPreview,
    InvitationTokenIn,
    PasswordResetIn,
    RoleIn,
)
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.passwords import checked_login, checked_password
from nestor.admin.api.v1.security import Caller, allowed, same_origin
from nestor.admin.api.v1.session.schemas import MeOut
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Scope

router = APIRouter(tags=["accounts"])
Manager = Annotated[Caller, Depends(allowed(Scope.ACCOUNTS_MANAGE))]


# -- accounts -----------------------------------------------------------------------------------------


@router.get("/accounts")
async def list_accounts(request: Request, caller: Manager) -> list[AccountOut]:
    admin = state(request)
    people = People(admin.nestor.household)
    return [AccountOut.of(a, people, admin.accounts) for a in admin.accounts.listed()]


@router.get("/accounts/{account_id}")
async def get_account(request: Request, caller: Manager, account_id: str) -> AccountOut:
    admin = state(request)
    return AccountOut.of(admin.accounts.get(account_id), People(admin.nestor.household), admin.accounts)


@router.put("/accounts/{account_id}/role")
async def change_account_role(request: Request, caller: Manager, account_id: str, body: RoleIn) -> AccountOut:
    """409 `last_owner` when it would leave no owner."""
    admin = state(request)
    account = await admin.accounts.change_role(account_id, body.role, by=caller.principal)
    return AccountOut.of(account, People(admin.nestor.household), admin.accounts)


@router.post("/accounts/{account_id}/disable")
async def disable_account(request: Request, caller: Manager, account_id: str) -> AccountOut:
    """The account can no longer sign in and its sessions end at once. 409 `last_owner` for the last owner."""
    admin = state(request)
    account = await admin.accounts.disable(account_id, by=caller.principal)
    admin.sessions.revoke(account.id)
    return AccountOut.of(account, People(admin.nestor.household), admin.accounts)


@router.post("/accounts/{account_id}/enable")
async def enable_account(request: Request, caller: Manager, account_id: str) -> AccountOut:
    admin = state(request)
    account = await admin.accounts.enable(account_id, by=caller.principal)
    return AccountOut.of(account, People(admin.nestor.household), admin.accounts)


@router.put("/accounts/{account_id}/password", status_code=204)
async def reset_account_password(request: Request, caller: Manager, account_id: str, body: PasswordResetIn) -> Response:
    """Set someone else's password (one's own goes through `PUT /me/password`); their sessions end."""
    admin = state(request)
    if account_id == caller.account_id:
        raise ApiError(400, "use_me_password")
    await admin.accounts.set_password(account_id, checked_password(body.password), by=caller.principal)
    admin.sessions.revoke(account_id)
    return Response(status_code=204)


# -- invitations ---------------------------------------------------------------------------------------


@router.get("/invitations")
async def list_invitations(request: Request, caller: Manager) -> list[InvitationOut]:
    admin = state(request)
    people = People(admin.nestor.household)
    invitations = sorted(admin.accounts.invitations.values(), key=lambda i: i.created_at, reverse=True)
    return [InvitationOut.of(i, people, admin.accounts) for i in invitations]


@router.post("/invitations", status_code=201)
async def create_invitation(request: Request, caller: Manager, body: InvitationIn) -> InvitationCreated:
    """A single-use link, valid 48 hours, carrying the role and the person."""
    admin = state(request)
    person = PersonId(body.person) if body.person else None
    invitation, token = await admin.accounts.invite(body.role, person, by=caller.principal)
    return InvitationCreated(
        invitation=InvitationOut.of(invitation, People(admin.nestor.household), admin.accounts),
        token=str(token),
        url=f"{admin.base_url(request)}/invitation#token={token}",
    )


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(request: Request, caller: Manager, invitation_id: str) -> Response:
    await state(request).accounts.revoke_invitation(invitation_id, by=caller.principal)
    return Response(status_code=204)


@router.post("/invitations/inspect", dependencies=[Depends(same_origin)])
async def inspect_invitation(request: Request, body: InvitationTokenIn) -> InvitationPreview:
    """What an invitation offers, before accepting it (no session needed)."""
    admin = state(request)
    invitation = await admin.accounts.invitation(body.token)
    return InvitationPreview.of(invitation, People(admin.nestor.household))


@router.post("/invitations/accept", status_code=201, dependencies=[Depends(same_origin)])
async def accept_invitation(request: Request, response: Response, body: InvitationAcceptIn) -> MeOut:
    """Open the account with a login and a password of one's choice; the new account is signed in."""
    admin = state(request)
    account = await admin.accounts.accept(
        body.token, login=checked_login(body.login), password=checked_password(body.password)
    )
    return MeOut.of(admin, account, admin.cookie.open(response, account.id, secure=admin.secure(request)))
