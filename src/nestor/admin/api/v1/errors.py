"""Errors of the API: always `{"error": {"code", "message_id", "args", "message"}}` — the code for
programs, the message id and arguments for a front with its own catalogue, the message rendered in
the reader's language. A message never holds a secret.
"""

from collections.abc import Mapping

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from nestor.admin.api.v1.language import reader_locale
from nestor.admin.state import state
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale, Localizer, Message
from nestor.core.i18n.types import Argument
from nestor.modules.accounts import (
    AccessDenied,
    AccountConflict,
    InvitationRefused,
    LastOwner,
    UnknownAccount,
    WrongPassword,
)


class ApiError(Exception):
    """`code` is snake_case; its message is `error-<code with dashes>`, with `args`."""

    def __init__(self, status: int, code: str, *, headers: Mapping[str, str] | None = None, **args: Argument) -> None:
        super().__init__(f"{status} {code}")
        self.status, self.code, self.headers = status, code, dict(headers or {})
        self.message = Message(f"error-{code.replace('_', '-')}", args)


def not_found(what: str = "not_found") -> ApiError:
    """404 with the message that says what is missing (`connection_unknown`…)."""
    return ApiError(404, what)


_INVITATIONS = {
    "this invitation has already been used": "invitation_used",
    "this invitation has expired: ask for a new one": "invitation_expired",
    "this invitation was withdrawn": "invitation_revoked",
}
_HTTP = {404: "not_found", 405: "method_not_allowed"}


def translate(error: Exception) -> ApiError:
    """The API error a domain or framework error stands for."""
    match error:
        case ApiError():
            return error
        case AccessDenied():
            return ApiError(403, "forbidden")
        case UnknownAccount():
            return not_found()
        case LastOwner():
            return ApiError(409, "last_owner")
        case AccountConflict():
            return ApiError(409, "conflict")
        case InvitationRefused():
            return ApiError(400, _INVITATIONS.get(str(error), "invitation_unknown"))
        case WrongPassword():
            return ApiError(400, "wrong_password")
        case ProviderError():
            return ApiError(502, "provider_error", detail=str(error))
        case ContractError():
            return ApiError(400, "invalid", detail=str(error))
        case RequestValidationError():
            fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "body" for e in error.errors())
            return ApiError(422, "invalid_request", fields=fields)
    assert isinstance(error, HTTPException), error  # the last type the application hands here
    return ApiError(error.status_code, _HTTP.get(error.status_code, "http_error"))


def respond(error: ApiError, localizer: Localizer, locale: Locale) -> JSONResponse:
    body = {
        "error": {
            "code": error.code,
            "message_id": error.message.id,
            "args": dict(error.message.args),
            "message": localizer.format(error.message, locale),
        }
    }
    return JSONResponse(body, status_code=error.status, headers=error.headers or None)


def localized(request: Request, error: Exception) -> JSONResponse:
    """The error, in the language of whoever made the request."""
    return respond(translate(error), state(request).nestor.localizer, reader_locale(request))
