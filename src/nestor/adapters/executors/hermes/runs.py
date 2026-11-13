"""What Hermes's Runs API answers, as Nestor reads it: replies, a run's state and its steps."""

import json
from typing import Any
from urllib.parse import quote

import httpx

from nestor.adapters.executors.common import step
from nestor.modules.cognition import Outcome


class UnexpectedReply(Exception):
    """Hermes answered with an error status or something that is not its protocol."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = status == 429 or (status or 0) >= 500


def run_outcome(status: str, payload: dict[str, Any]) -> Outcome | None:
    match status:
        case "completed":
            return Outcome.completed(str(payload.get("output") or ""))
        case "failed":
            return Outcome.failed(error_text(payload.get("error")) or "Hermes reported the run as failed")
        case "cancelled":
            return Outcome.cancelled()
        case _:
            return None


def error_text(error: object) -> str | None:
    if isinstance(error, dict):
        error = error.get("message")
    return str(error) if error else None


def run_step(event: dict[str, Any]) -> str:
    tool, preview = event.get("tool") or "tool", event.get("preview")
    return step(f"{tool}: {preview}" if preview else str(tool))


def payload(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise UnexpectedReply(f"HTTP {response.status_code}: {response.text[:200]}", response.status_code)
    return decode(response.text)


def decode(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError:
        raise UnexpectedReply(f"not JSON: {text[:200]!r}") from None
    if not isinstance(data, dict):
        raise UnexpectedReply(f"not a JSON object: {text[:200]!r}")
    return data


def run_path(ref: str) -> str:
    return f"runs/{quote(ref, safe='')}"
