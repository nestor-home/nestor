"""What the account book refuses."""

from nestor.core import ContractError
from nestor.modules.accounts.types import InvitationStatus


class UnknownAccount(ContractError):
    """No such account or invitation."""


class AccountConflict(ContractError):
    """The login is taken, or the person already has an account."""


class PersonRequired(ContractError):
    """A member or guest account belongs to a person of the household."""


class UnknownPerson(ContractError):
    """The household has no such person."""


class LastOwner(ContractError):
    """The change would leave the household without an owner."""


class InvitationRefused(ContractError):
    """An invitation that is unknown, expired, revoked or already used. `status` says which, for programs:
    `None` when the invitation is unknown."""

    def __init__(self, message: str, *, status: InvitationStatus | None = None) -> None:
        super().__init__(message)
        self.status = status


class WrongPassword(ContractError):
    """Changing one's own password needs the current one."""
