"""Roles and sign-in failures as the household reads them."""

from nestor.modules.accounts import Role

_ROLES = {Role.OWNER: "propriétaire", Role.ADMIN: "administrateur", Role.MEMBER: "membre", Role.GUEST: "invité"}
_FAILURES = {
    "wrong password": "mot de passe incorrect",
    "unknown login": "identifiant inconnu",
    "disabled": "compte désactivé",
}


def french_role(role: Role) -> str:
    return _ROLES[role]


def french_login_failure(reason: str) -> str:
    return _FAILURES.get(reason, reason)
