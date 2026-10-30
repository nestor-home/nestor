"""Account events. Never a password, a hash or a token: those stay in the verifier store."""

from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.accounts.permissions import Role


class AccountCreated(Event, event_type="account.created"):
    account_id: str
    login: str
    role: Role
    person: PersonId | None = None
    invitation_id: str | None = None  # the invitation it was opened with
    created_by: str | None = None  # None: from the command line


class AccountRoleChanged(Event, event_type="account.role.changed"):
    account_id: str
    role: Role
    by: str | None = None


class AccountDisabled(Event, event_type="account.disabled"):
    account_id: str
    by: str | None = None


class AccountEnabled(Event, event_type="account.enabled"):
    account_id: str
    by: str | None = None


class AccountPasswordChanged(Event, event_type="account.password.changed"):
    account_id: str
    by: str | None = None  # the account itself, an administrator resetting it, or the command line


class AccountInvited(Event, event_type="account.invited"):
    invitation_id: str
    role: Role
    person: PersonId | None
    expires_at: datetime
    invited_by: str | None = None


class InvitationRevoked(Event, event_type="account.invitation.revoked"):
    invitation_id: str
    by: str | None = None


class AccountLogin(Event, event_type="account.login"):
    """A sign-in attempt. A failure for an unknown login names no account: the typed login is not kept
    (it is sometimes a password typed in the wrong field)."""

    succeeded: bool
    account_id: str | None = None
    client: str = ""
    reason: str = ""  # why it failed: "wrong password", "unknown login", "disabled"
