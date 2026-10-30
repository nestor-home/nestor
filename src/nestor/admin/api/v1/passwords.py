"""New passwords and logins checked at the API, so the refusal is said in French."""

from nestor.admin.api.v1.errors import ApiError
from nestor.core import ContractError
from nestor.modules.accounts import MIN_LENGTH, normalise_login


def checked_password(password: str) -> str:
    if len(password) < MIN_LENGTH:
        raise ApiError(400, "weak_password", f"Choisissez un mot de passe d'au moins {MIN_LENGTH} caractères.")
    return password


def checked_login(login: str) -> str:
    try:
        return normalise_login(login)
    except ContractError:
        raise ApiError(
            400, "invalid_login", "L'identifiant est un e-mail ou un nom d'utilisateur (lettres, chiffres, . _ + @ -)."
        ) from None
