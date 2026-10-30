"""What the account book refuses."""

from nestor.core import ContractError


class UnknownAccount(ContractError):
    """No such account or invitation."""


class AccountConflict(ContractError):
    """The login is taken, or the person already has an account."""


class LastOwner(ContractError):
    """The change would leave the household without an owner."""


class InvitationRefused(ContractError):
    """An invitation that is unknown, expired, revoked or already used."""


class WrongPassword(ContractError):
    """Changing one's own password needs the current one."""
