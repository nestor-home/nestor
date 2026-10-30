"""Errors of the API: always `{"error": {"code", "message"}}`, the code for programs, the message in
French for the person. A message never holds a secret."""

from collections.abc import Mapping

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from nestor.core import ContractError, ProviderError
from nestor.modules.accounts import (
    AccessDenied,
    AccountConflict,
    InvitationRefused,
    LastOwner,
    UnknownAccount,
    WrongPassword,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.headers = status, code, message, dict(headers or {})


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", what)


FORBIDDEN = "Votre compte n'a pas accès à cette fonction."
_INVITATIONS = {
    "this invitation has already been used": "Cette invitation a déjà servi.",
    "this invitation has expired: ask for a new one": "Cette invitation a expiré : demandez-en une nouvelle.",
    "this invitation was withdrawn": "Cette invitation a été retirée.",
}
_HTTP = {404: ("not_found", "Cette adresse n'existe pas."), 405: ("method_not_allowed", "Méthode non permise.")}


def translate(error: Exception) -> ApiError:
    """The API error a domain or framework error stands for."""
    match error:
        case ApiError():
            return error
        case AccessDenied():
            return ApiError(403, "forbidden", FORBIDDEN)
        case UnknownAccount():
            return not_found("Ce compte ou cette invitation n'existe pas.")
        case LastOwner():
            return ApiError(409, "last_owner", "Le foyer doit garder au moins un propriétaire : nommez-en un autre.")
        case AccountConflict():
            return ApiError(409, "conflict", "Cet identifiant est déjà pris, ou cette personne a déjà un compte.")
        case InvitationRefused():
            message = _INVITATIONS.get(str(error), "Cette invitation est inconnue.")
            return ApiError(400, "invitation_refused", message)
        case WrongPassword():
            return ApiError(400, "wrong_password", "Le mot de passe actuel est incorrect.")
        case ProviderError():
            return ApiError(502, "provider_error", f"Le service n'a pas pu répondre : {error}.")
        case ContractError():
            return ApiError(400, "invalid", f"Action impossible : {error}.")
        case RequestValidationError():
            fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "corps" for e in error.errors())
            return ApiError(422, "invalid_request", f"Requête invalide ({fields}).")
    assert isinstance(error, HTTPException), error  # the last type the application hands here
    code, message = _HTTP.get(error.status_code, ("http_error", "Requête refusée."))
    return ApiError(error.status_code, code, message)


def respond(error: ApiError) -> JSONResponse:
    body = {"error": {"code": error.code, "message": error.message}}
    return JSONResponse(body, status_code=error.status, headers=error.headers or None)
