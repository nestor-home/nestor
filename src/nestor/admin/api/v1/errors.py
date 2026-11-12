"""Errors of the API: always `{"error": {"code", "message_id", "args", "message"}}` — the code for
programs, the message id and arguments for a front with its own catalogue, the message rendered in
the reader's language. A message never holds a secret.
"""

from collections.abc import Mapping
from typing import Any, Literal

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from nestor.admin.api.v1.language import reader_locale
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import state
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale, Localizer, Message
from nestor.core.i18n.types import Argument
from nestor.modules.accounts import (
    AccessDenied,
    AccountConflict,
    InvitationRefused,
    InvitationStatus,
    LastOwner,
    PersonRequired,
    UnknownAccount,
    UnknownPerson,
    WrongPassword,
)
from nestor.runtime.config import ProblemCode
from nestor.runtime.editing import Problem, dotted

# Every code the API sends: the type checker refuses any other, and the OpenAPI document lists them for the front.
ErrorCode = Literal[
    "addition_over",
    "addition_unknown",
    "attachment_unknown",
    "audio_format",
    "bad_token",
    "chat_busy",
    "chat_needs_person",
    "chat_off",
    "client_incomplete",
    "client_missing",
    "config_history_unknown",
    "config_invalid",
    "config_unavailable",
    "conflict",
    "connection_unknown",
    "connector_unknown",
    "cross_origin",
    "csrf_failed",
    "empty_memory",
    "fields_missing",
    "forbidden",
    "http_error",
    "identify_unsupported",
    "invalid",
    "invalid_code",
    "invalid_credentials",
    "invalid_login",
    "invalid_request",
    "invitation_expired",
    "invitation_revoked",
    "invitation_unknown",
    "invitation_used",
    "journal_entry_unknown",
    "last_owner",
    "memory_shared",
    "memory_unknown",
    "method_not_allowed",
    "no_connectors",
    "no_secret_key",
    "not_a_device_code_method",
    "not_found",
    "not_oauth",
    "oauth",
    "own_connections_only",
    "pairing_refused",
    "pending_unknown",
    "person_required",
    "person_unknown",
    "provider_error",
    "provider_refused",
    "restart_unconfirmed",
    "satellite_offline",
    "satellite_unknown",
    "secret_in_use",
    "secret_unknown",
    "task_unknown",
    "throttled",
    "too_many_additions",
    "unauthenticated",
    "unknown_locale",
    "unknown_person",
    "unknown_tool",
    "unsupported_media_type",
    "update_not_installable",
    "update_unavailable",
    "update_unconfirmed",
    "update_unsupported",
    "use_me_password",
    "voice_not_yours",
    "voices_off",
    "watch_unknown",
    "schedule_unknown",
    "confirmation_unknown",
    "weak_password",
    "wrong_password",
]


class ProblemOut(BaseModel):
    """What is wrong in an edited configuration, located by its path in the document."""

    path: list[str | int]  # `["channels", 0, "token"]`; empty: the document as a whole
    code: ProblemCode
    message_id: str  # `config-error-<code>`, with `args` {path, detail}
    args: dict[str, str | int | float]
    message: str

    @classmethod
    def of(cls, problem: Problem, words: Phrasebook) -> "ProblemOut":
        message = Message.of(
            f"config-error-{problem.code.replace('_', '-')}", path=dotted(problem.path), detail=problem.detail
        )
        return cls(
            path=list(problem.path),
            code=problem.code,
            message_id=message.id,
            args=dict(message.args),
            message=words.text(message),
        )


class ErrorDetail(BaseModel):
    code: ErrorCode  # for programs: `invalid_credentials`, `last_owner`…
    message_id: str  # `error-<code with dashes>`, for a front rendering with its own catalogue
    args: dict[str, str | int | float]
    message: str  # rendered in the reader's language, shown as is
    problems: list[ProblemOut] | None = None  # a configuration refused: what is wrong, where


class ErrorOut(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    """`code` is snake_case; its message is `error-<code with dashes>`, with `args`."""

    def __init__(
        self,
        status: int,
        code: ErrorCode,
        *,
        headers: Mapping[str, str] | None = None,
        problems: list[dict[str, Any]] | None = None,
        **args: Argument,
    ) -> None:
        super().__init__(f"{status} {code}")
        self.status, self.code, self.headers, self.problems = status, code, dict(headers or {}), problems
        self.message = Message(f"error-{code.replace('_', '-')}", args)


def not_found(what: ErrorCode = "not_found") -> ApiError:
    """404 with the message that says what is missing (`connection_unknown`…)."""
    return ApiError(404, what)


_INVITATIONS: dict[InvitationStatus, ErrorCode] = {
    InvitationStatus.ACCEPTED: "invitation_used",
    InvitationStatus.EXPIRED: "invitation_expired",
    InvitationStatus.REVOKED: "invitation_revoked",
}
_HTTP: dict[int, ErrorCode] = {404: "not_found", 405: "method_not_allowed"}


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
        case InvitationRefused(status=InvitationStatus() as status):
            return ApiError(400, _INVITATIONS[status])
        case InvitationRefused():
            return ApiError(400, "invitation_unknown")
        case WrongPassword():
            return ApiError(400, "wrong_password")
        case UnknownPerson():
            return ApiError(400, "unknown_person")
        case PersonRequired():
            return ApiError(400, "person_required")
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
            **({"problems": error.problems} if error.problems is not None else {}),
        }
    }
    return JSONResponse(body, status_code=error.status, headers=error.headers or None)


def localized(request: Request, error: Exception) -> JSONResponse:
    """The error, in the language of whoever made the request."""
    return respond(translate(error), state(request).nestor.localizer, reader_locale(request))
