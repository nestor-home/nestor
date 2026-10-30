"""Hermes as a remote executor, through its Runs HTTP API.

A run is started with `POST runs`, followed on `GET runs/{id}/events` (server-sent events) and
stopped with `POST runs/{id}/stop`; `GET runs/{id}` gives its state. Observed on a Hermes server
(2026-10-30): a finished run's state carries its `status` and `output`, and the events stream of a
finished run replays every event up to the terminal one, then closes. Following a run therefore
reads its state first and only streams while it is still going, which also makes `follow` safe to
call again after a restart.
"""

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import PositiveFloat, SecretStr

from nestor.core import ContractError, ProviderError
from nestor.modules.cognition import Outcome, Progress, RemoteExecutor
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings

INSTRUCTIONS = (
    "You carry out a task handed over by a home voice assistant. Use your tools and check the result, "
    "then write a short, factual report in the language of the task: what was done or found, and what "
    "could not be. No Markdown: the assistant will say it aloud. Never claim an action you did not perform."
)
MAX_STEP_LENGTH = 160


class _UnexpectedReply(Exception):
    """Hermes answered with an error status or something that is not its protocol."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = status == 429 or (status or 0) >= 500


class HermesExecutor(RemoteExecutor):
    """Delegates objectives to a Hermes agent profile; its runs outlive Nestor.

    `description` states what this Hermes profile's tools really allow: the assistant promises
    exactly that. Stream reads have no timeout (a run may take minutes); connections and plain
    requests time out after `timeout_s`.
    """

    name = "hermes"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        description: str,
        instructions: str = INSTRUCTIONS,
        timeout_s: float = 15.0,
        stop_timeout_s: float = 10.0,
        poll_interval_s: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.description = description
        self._base_url, self._api_key, self._model, self._instructions = base_url, api_key, model, instructions
        self._timeout_s, self._stop_timeout_s, self._poll_interval_s = timeout_s, stop_timeout_s, poll_interval_s
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout_s,
                transport=self._transport,
            )

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def submit(self, objective: str) -> str:
        body = {"model": self._model, "input": objective, "instructions": self._instructions}
        try:
            reply = _payload(await self._http.post("runs", json=body))
        except httpx.HTTPError as error:
            raise ProviderError(self.name, f"submission failed: {_describe(error)}", transient=True) from error
        except _UnexpectedReply as error:
            raise ProviderError(self.name, f"submission refused: {error}", transient=error.retryable) from error
        run_id = reply.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ProviderError(self.name, f"no run id in the submission reply: {reply}", transient=False)
        return run_id

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        try:
            outcome = await self._finished(ref) or await self._stream(ref, progress) or await self._finished(ref)
        except httpx.HTTPError as error:
            return Outcome.failed(f"lost contact with Hermes: {_describe(error)}")
        except _UnexpectedReply as error:
            return Outcome.failed(f"unexpected reply from Hermes: {error}")
        return outcome or Outcome.failed("Hermes event stream ended before the run finished")

    async def stop(self, ref: str) -> bool:
        try:
            async with asyncio.timeout(self._stop_timeout_s):
                _payload(await self._http.post(f"{_run_path(ref)}/stop"))
                while True:
                    status = (await self._state(ref)).get("status")
                    if status == "cancelled":
                        return True
                    if status in ("completed", "failed"):
                        return False  # finished on its own before the stop
                    await asyncio.sleep(self._poll_interval_s)
        except (TimeoutError, httpx.HTTPError, _UnexpectedReply):
            return False

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ContractError(f"{self.name} executor used before start()")
        return self._client

    async def _state(self, ref: str) -> dict[str, Any]:
        return _payload(await self._http.get(_run_path(ref)))

    async def _finished(self, ref: str) -> Outcome | None:
        """The run's outcome if it is over, `None` while it runs."""
        state = await self._state(ref)
        return _outcome(str(state.get("status")), state)

    async def _stream(self, ref: str, progress: Progress) -> Outcome | None:
        """Follows the run's events until its terminal one; `None` if the stream ends before."""
        timeout = httpx.Timeout(self._timeout_s, read=None)
        async with self._http.stream("GET", f"{_run_path(ref)}/events", timeout=timeout) as events:
            if events.is_error:
                await events.aread()
                _payload(events)
            async for line in events.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = _decode(line.removeprefix("data:"))
                name = str(event.get("event"))
                if name == "tool.started":
                    progress(_step(event))
                elif name.startswith("run.") and (outcome := _outcome(name.removeprefix("run."), event)):
                    return outcome
        return None


def _outcome(status: str, payload: dict[str, Any]) -> Outcome | None:
    match status:
        case "completed":
            return Outcome.completed(str(payload.get("output") or ""))
        case "failed":
            return Outcome.failed(_error_text(payload.get("error")) or "Hermes reported the run as failed")
        case "cancelled":
            return Outcome.cancelled()
        case _:
            return None


def _error_text(error: object) -> str | None:
    if isinstance(error, dict):
        error = error.get("message")
    return str(error) if error else None


def _step(event: dict[str, Any]) -> str:
    tool, preview = event.get("tool") or "tool", event.get("preview")
    return (f"{tool}: {preview}" if preview else str(tool))[:MAX_STEP_LENGTH]


def _payload(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise _UnexpectedReply(f"HTTP {response.status_code}: {response.text[:200]}", response.status_code)
    return _decode(response.text)


def _decode(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError:
        raise _UnexpectedReply(f"not JSON: {text[:200]!r}") from None
    if not isinstance(data, dict):
        raise _UnexpectedReply(f"not a JSON object: {text[:200]!r}")
    return data


def _describe(error: httpx.HTTPError) -> str:
    return f"{type(error).__name__} {error}".strip()


def _run_path(ref: str) -> str:
    return f"runs/{quote(ref, safe='')}"


class HermesSettings(AdapterSettings):
    base_url: str  # including the API version, e.g. https://hermes.example/v1
    api_key: SecretStr
    model: str  # the Hermes agent profile
    description: str  # what this profile's tools really allow
    instructions: str = INSTRUCTIONS
    timeout_s: PositiveFloat = 15.0
    stop_timeout_s: PositiveFloat = 10.0


def build(settings: HermesSettings, name: str, services: Services) -> HermesExecutor:
    executor = HermesExecutor(
        settings.base_url,
        settings.api_key.get_secret_value(),
        settings.model,
        description=settings.description,
        instructions=settings.instructions,
        timeout_s=settings.timeout_s,
        stop_timeout_s=settings.stop_timeout_s,
    )
    executor.name = name  # two Hermes profiles are two executors
    return executor


plugin = Plugin(Family.EXECUTOR, "hermes", HermesSettings, build)
