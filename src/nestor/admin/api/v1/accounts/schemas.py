"""Accounts and invitations as the API takes and sends them; `AccountOut` is shared with the household."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import Input, People, PersonRef
from nestor.modules.accounts import Accounts, Invitation, InvitationStatus, Role


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
    person: PersonRef | None
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime

    @classmethod
    def of(cls, invitation: Invitation, people: People, accounts: Accounts) -> "InvitationOut":
        return cls(
            id=invitation.id,
            role=invitation.role,
            person=people.ref(invitation.person),
            status=invitation.status(accounts.now()),
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )


class InvitationCreated(BaseModel):
    invitation: InvitationOut
    token: str  # shown once, here only: the front builds nothing from it but `url`
    url: str  # the link to give the invited person; the token is in its fragment, never sent to a server


class InvitationTokenIn(Input):
    token: str


class InvitationPreview(BaseModel):
    role: Role
    person: PersonRef | None
    expires_at: datetime

    @classmethod
    def of(cls, invitation: Invitation, people: People) -> "InvitationPreview":
        return cls(role=invitation.role, person=people.ref(invitation.person), expires_at=invitation.expires_at)


class InvitationAcceptIn(Input):
    token: str
    login: str
    password: str
