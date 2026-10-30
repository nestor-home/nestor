"""Accounts of the admin and invitations to open one."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nestor.core import ContractError, PersonId
from nestor.modules.accounts.permissions import GRANTS, Principal, Role

_LOGIN = re.compile(r"^[a-z0-9][a-z0-9._+@-]{1,99}$")


def normalise_login(text: str) -> str:
    """An email or a username, compared without case: `Mathis@Example.org` is `mathis@example.org`."""
    login = text.strip().casefold()
    if not _LOGIN.match(login):
        raise ContractError("a login is an email or a username: letters, digits and . _ + @ - (2 to 100)")
    return login


@dataclass(frozen=True, slots=True, kw_only=True)
class Account:
    """Someone who signs in to the admin.

    Members and guests are always a person of the household: what they may read is defined by that
    person. Owners and admins usually are one too, but need not be — an installer's technical account
    sees everything through its scopes and has no "own" data.
    """

    id: str
    login: str
    role: Role
    person: PersonId | None = None
    disabled: bool = False
    created_at: datetime

    def principal(self) -> Principal:
        scopes = frozenset() if self.disabled else GRANTS[self.role]
        return Principal(scopes=scopes, person=self.person, account_id=self.id)


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True, kw_only=True)
class Invitation:
    """A single-use, expiring offer to open an account with this role, for this person."""

    id: str
    role: Role
    person: PersonId | None
    invited_by: str | None  # account id
    created_at: datetime
    expires_at: datetime
    accepted_by: str | None = None  # the account opened with it
    revoked: bool = False

    def status(self, now: datetime) -> InvitationStatus:
        if self.accepted_by is not None:
            return InvitationStatus.ACCEPTED
        if self.revoked:
            return InvitationStatus.REVOKED
        return InvitationStatus.EXPIRED if self.expires_at <= now else InvitationStatus.PENDING
