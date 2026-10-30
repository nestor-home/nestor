"""Accounts: who signs in to the admin, with which role, and what each scope lets them do.

Every account has a role; roles grant named scopes in one table (`GRANTS`) and code only ever checks
scopes. Accounts are rebuilt from the journal; password hashes and invitation digests live in a
`VerifierStore`, never in an event. There is always at least one active owner.
"""

from nestor.modules.accounts.activity import ActivityStore
from nestor.modules.accounts.credentials import MIN_LENGTH, Token, VerifierStore, hash_password, verify_password
from nestor.modules.accounts.errors import AccountConflict, InvitationRefused, LastOwner, UnknownAccount, WrongPassword
from nestor.modules.accounts.events import (
    AccountCreated,
    AccountDisabled,
    AccountEnabled,
    AccountInvited,
    AccountLocaleChanged,
    AccountLogin,
    AccountPasswordChanged,
    AccountRoleChanged,
    InvitationRevoked,
)
from nestor.modules.accounts.permissions import GRANTS, AccessDenied, Principal, Role, Scope
from nestor.modules.accounts.service import INVITATION_TTL, Accounts
from nestor.modules.accounts.types import Account, Invitation, InvitationStatus, normalise_login

__all__ = [
    "GRANTS",
    "INVITATION_TTL",
    "MIN_LENGTH",
    "AccessDenied",
    "Account",
    "AccountConflict",
    "AccountCreated",
    "AccountDisabled",
    "AccountEnabled",
    "AccountInvited",
    "AccountLocaleChanged",
    "AccountLogin",
    "AccountPasswordChanged",
    "AccountRoleChanged",
    "Accounts",
    "ActivityStore",
    "Invitation",
    "InvitationRefused",
    "InvitationRevoked",
    "InvitationStatus",
    "LastOwner",
    "Principal",
    "Role",
    "Scope",
    "Token",
    "UnknownAccount",
    "VerifierStore",
    "WrongPassword",
    "hash_password",
    "normalise_login",
    "verify_password",
]
