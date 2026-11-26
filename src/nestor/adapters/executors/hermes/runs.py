"""What Hermes's Runs API answers, as Nestor reads it: replies, how a run ended, its steps."""

import json
from typing import Any
from urllib.parse import quote

import httpx

from nestor.adapters.executors.common import Report
from nestor.modules.cognition import Outcome

# Tools whose preview says what they look at (a query, a page); any other shows its name only: a preview of the
# others may be a shell command or code, and the household reads the steps.
SHOWN = frozenset({"web_search", "web_extract", "browser_navigate", "vision_analyze", "image_generate"})
UNDELIVERED = "Instruction given while it worked, not delivered before the turn ended: {text}"


class UnexpectedReply(Exception):
    """Hermes answered with an error status or something that is not its protocol."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = status == 429 or (status or 0) >= 500


def run_outcome(status: str, fields: dict[str, Any], session: str | None) -> Outcome | None:
    """How a run in `status` ended, from its terminal event or state; `None` while it goes on."""
    pending = fields.get("pending_steer")
    undelivered = UNDELIVERED.format(text=pending) if isinstance(pending, str) and pending.strip() else None
    match status:
        case "completed":
            report = Report.of(str(fields.get("output") or ""))
            text = "\n".join(t for t in (report.text, undelivered) if t)
            if report.question:
                return Outcome.asked(report.question, text, session=session)
            return Outcome.completed(text, session=session)
        case "failed" | "interrupted":
            error = error_text(fields.get("error")) or f"Hermes reported the run as {status}"
            return Outcome.failed("\n".join(t for t in (error, undelivered) if t), session=session)
        case "cancelled":
            return Outcome.stopped(session=session)
        case _:
            return None


def clarified(prompt: dict[str, Any]) -> str | None:
    """The question of a `clarify` prompt, with its choices when it offers some."""
    question = str(prompt.get("question") or "").strip()
    choices = [str(c).strip() for c in prompt.get("choices") or () if str(c).strip()]
    if not question:
        return None
    return f"{question} ({' / '.join(choices)})" if choices else question


def waiting_on(state: dict[str, Any]) -> str | None:
    """The question a running run waits on (`clarify`), from its state's pending controls."""
    for prompt in state.get("pending_controls") or ():
        if isinstance(prompt, dict) and prompt.get("kind") == "clarify" and (question := clarified(prompt)):
            return question
    return None


def error_text(error: object) -> str | None:
    if isinstance(error, dict):
        error = error.get("message")
    return str(error) if error else None


def run_step(event: dict[str, Any]) -> str:
    tool, preview = str(event.get("tool") or "tool"), event.get("preview")
    return f"{tool}: {preview}" if preview and tool in SHOWN else tool


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
