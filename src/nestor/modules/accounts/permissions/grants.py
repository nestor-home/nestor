"""The one table that grants scopes to roles."""

from collections.abc import Mapping

from nestor.modules.accounts.permissions.types import Role, Scope

_OWN = frozenset({Scope.JOURNAL_READ_OWN, Scope.MEMORY_MANAGE_OWN})
_MEMBER = _OWN | {
    Scope.HOUSEHOLD_READ,
    Scope.OWN_CONNECTIONS,
    Scope.TASKS_MANAGE_OWN,
    Scope.WATCHES_MANAGE_OWN,
}
_ADMIN = _MEMBER | {
    Scope.ACCOUNTS_MANAGE,
    Scope.HOUSEHOLD_CONNECTIONS,
    Scope.SATELLITES_MANAGE,
    Scope.SYSTEM_READ,
    Scope.CONFIG_MANAGE,
    Scope.JOURNAL_READ_ALL,
    Scope.MEMORY_MANAGE_ALL,
    Scope.TASKS_MANAGE,
    Scope.WATCHES_MANAGE_ALL,
}

GRANTS: Mapping[Role, frozenset[Scope]] = {
    Role.OWNER: frozenset(Scope),
    Role.ADMIN: _ADMIN,
    Role.MEMBER: _MEMBER,
    Role.GUEST: _OWN,
}
