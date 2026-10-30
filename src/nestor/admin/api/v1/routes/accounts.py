"""Accounts and invitations: who may sign in, with which role. Owners are touched only by owners."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.models import AccountOut, Input, People, PersonRef
from nestor.admin.api.v1.passwords import checked_login, checked_password
from nestor.admin.api.v1.routes.session import MeOut, open_session
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import french_role
from nestor.admin.state import AdminState, state
from nestor.core import PersonId
from nestor.modules.accounts import Invitation, InvitationStatus, Role, Scope

router = APIRouter(tags=["accounts"])
Manager = Annotated[Caller, Depends(allowed(Scope.ACCOUNTS_MANAGE))]


class RoleIn(Input):
    role: Role


class PasswordResetIn(Input):
    password: str


class InvitationIn(Input):
    role: Role
    person: str | None = None  # required for members and guests


class InvitationOut(BaseModel):
    id: str
    role: Role
    role_label: str
    person: PersonRef | None
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime


class InvitationCreated(BaseModel):
    invitation: InvitationOut
    token: str  # shown once, here only: the front builds nothing from it but `url`
    url: str  # the link to give the invited person; the token is in its fragment, never sent to a server


class InvitationTokenIn(Input):
    token: str


class InvitationPreview(BaseModel):
    role: Role
    role_label: str
    person: PersonRef | None
    expires_at: datetime


class InvitationAcceptIn(Input):
    token: str
    login: str
    password: str


# -- accounts -----------------------------------------------------------------------------------------


@router.get("/accounts")
async def list_accounts(request: Request, caller: Manager) -> list[AccountOut]:
    admin = state(request)
    people = People(admin.nestor.household)
    return [AccountOut.of(a, people) for a in admin.accounts.listed()]


@router.put("/accounts/{account_id}/role")
async def change_account_role(request: Request, caller: Manager, account_id: str, body: RoleIn) -> AccountOut:
    """409 `last_owner` when it would leave no owner."""
    admin = state(request)
    account = await admin.accounts.change_role(account_id, body.role, by=caller.principal)
    return AccountOut.of(account, People(admin.nestor.household))


@router.post("/accounts/{account_id}/disable")
async def disable_account(request: Request, caller: Manager, account_id: str) -> AccountOut:
    """The account can no longer sign in and its sessions end at once. 409 `last_owner` for the last owner."""
    admin = state(request)
    account = await admin.accounts.disable(account_id, by=caller.principal)
    admin.sessions.revoke(account.id)
    return AccountOut.of(account, People(admin.nestor.household))


@router.post("/accounts/{account_id}/enable")
async def enable_account(request: Request, caller: Manager, account_id: str) -> AccountOut:
    admin = state(request)
    account = await admin.accounts.enable(account_id, by=caller.principal)
    return AccountOut.of(account, People(admin.nestor.household))


@router.put("/accounts/{account_id}/password", status_code=204)
async def reset_account_password(request: Request, caller: Manager, account_id: str, body: PasswordResetIn) -> Response:
    """Set someone else's password (one's own goes through `PUT /me/password`); their sessions end."""
    admin = state(request)
    if account_id == caller.account_id:
        raise ApiError(400, "use_me_password", "Pour votre propre mot de passe, passez par votre profil.")
    await admin.accounts.set_password(account_id, checked_password(body.password), by=caller.principal)
    admin.sessions.revoke(account_id)
    return Response(status_code=204)


# -- invitations ---------------------------------------------------------------------------------------


@router.get("/invitations")
async def list_invitations(request: Request, caller: Manager) -> list[InvitationOut]:
    admin = state(request)
    invitations = sorted(admin.accounts.invitations.values(), key=lambda i: i.created_at, reverse=True)
    return [_invitation(admin, i) for i in invitations]


@router.post("/invitations", status_code=201)
async def create_invitation(request: Request, caller: Manager, body: InvitationIn) -> InvitationCreated:
    """A single-use link, valid 48 hours, carrying the role and the person."""
    admin = state(request)
    if body.person is not None and not People(admin.nestor.household).known(body.person):
        raise ApiError(400, "unknown_person", "Choisissez une personne du foyer.")
    if body.person is None and body.role in (Role.MEMBER, Role.GUEST):
        raise ApiError(400, "person_required", "Un compte membre ou invité appartient à une personne du foyer.")
    person = PersonId(body.person) if body.person else None
    invitation, token = await admin.accounts.invite(body.role, person, by=caller.principal)
    url = f"{admin.base_url(request)}/invitation#token={token}"
    return InvitationCreated(invitation=_invitation(admin, invitation), token=str(token), url=url)


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(request: Request, caller: Manager, invitation_id: str) -> Response:
    await state(request).accounts.revoke_invitation(invitation_id, by=caller.principal)
    return Response(status_code=204)


@router.post("/invitations/inspect")
async def inspect_invitation(request: Request, body: InvitationTokenIn) -> InvitationPreview:
    """What an invitation offers, before accepting it (no session needed)."""
    admin = state(request)
    invitation = await admin.accounts.invitation(body.token)
    return InvitationPreview(
        role=invitation.role,
        role_label=french_role(invitation.role),
        person=People(admin.nestor.household).ref(invitation.person),
        expires_at=invitation.expires_at,
    )


@router.post("/invitations/accept", status_code=201)
async def accept_invitation(request: Request, response: Response, body: InvitationAcceptIn) -> MeOut:
    """Open the account with a login and a password of one's choice; the new account is signed in."""
    admin = state(request)
    account = await admin.accounts.accept(
        body.token, login=checked_login(body.login), password=checked_password(body.password)
    )
    return open_session(request, response, account)


def _invitation(admin: AdminState, invitation: Invitation) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        role=invitation.role,
        role_label=french_role(invitation.role),
        person=People(admin.nestor.household).ref(invitation.person),
        status=invitation.status(admin.accounts.now()),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )
