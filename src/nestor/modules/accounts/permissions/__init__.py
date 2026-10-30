"""Permissions: roles, the scopes they grant, and the principal whose scopes an action checks."""

from nestor.modules.accounts.permissions.grants import GRANTS
from nestor.modules.accounts.permissions.principal import AccessDenied, Principal
from nestor.modules.accounts.permissions.types import Role, Scope

__all__ = ["GRANTS", "AccessDenied", "Principal", "Role", "Scope"]
