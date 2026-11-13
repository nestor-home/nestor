"""A Hermes agent profile that runs Nestor's tasks."""

import asyncio
from typing import Any

import httpx

from nestor.adapters.executors.common import INSTRUCTIONS, described
from nestor.adapters.executors.hermes.runs import UnexpectedReply, decode, payload, run_outcome, run_path, run_step
from nestor.core import ContractError, ProviderError
from nestor.modules.cognition import Outcome, Progress, RemoteExecutor


class HermesExecutor(RemoteExecutor):
    """Delegates objectives to a Hermes agent profile; its runs outlive Nestor.

    `description` states what this Hermes profile's tools really allow: the assistant promises
    exactly that. Stream reads have no timeout (a run may take minutes); connections and plain
    requests time out after `timeout_s`.
    """

    name = "hermes"
    brand = "hermes"

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
            reply = payload(await self._http.post("runs", json=body))
        except httpx.HTTPError as error:
            raise ProviderError(self.name, f"submission failed: {described(error)}", transient=True) from error
        except UnexpectedReply as error:
            raise ProviderError(self.name, f"submission refused: {error}", transient=error.retryable) from error
        run_id = reply.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ProviderError(self.name, f"no run id in the submission reply: {reply}", transient=False)
        return run_id

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        try:
            outcome = await self._finished(ref) or await self._stream(ref, progress) or await self._finished(ref)
        except httpx.HTTPError as error:
            return Outcome.failed(f"lost contact with Hermes: {described(error)}")
        except UnexpectedReply as error:
            return Outcome.failed(f"unexpected reply from Hermes: {error}")
        return outcome or Outcome.failed("Hermes event stream ended before the run finished")

    async def stop(self, ref: str) -> bool:
        try:
            async with asyncio.timeout(self._stop_timeout_s):
                payload(await self._http.post(f"{run_path(ref)}/stop"))
                while True:
                    status = (await self._state(ref)).get("status")
                    if status == "cancelled":
                        return True
                    if status in ("completed", "failed"):
                        return False  # finished on its own before the stop
                    await asyncio.sleep(self._poll_interval_s)
        except (TimeoutError, httpx.HTTPError, UnexpectedReply):
            return False

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ContractError(f"{self.name} executor used before start()")
        return self._client

    async def _state(self, ref: str) -> dict[str, Any]:
        return payload(await self._http.get(run_path(ref)))

    async def _finished(self, ref: str) -> Outcome | None:
        """The run's outcome if it is over, `None` while it runs."""
        state = await self._state(ref)
        return run_outcome(str(state.get("status")), state)

    async def _stream(self, ref: str, progress: Progress) -> Outcome | None:
        """Follows the run's events until its terminal one; `None` if the stream ends before."""
        timeout = httpx.Timeout(self._timeout_s, read=None)
        async with self._http.stream("GET", f"{run_path(ref)}/events", timeout=timeout) as events:
            if events.is_error:
                await events.aread()
                payload(events)
            async for line in events.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = decode(line.removeprefix("data:"))
                name = str(event.get("event"))
                if name == "tool.started":
                    progress(run_step(event))
                elif name.startswith("run.") and (outcome := run_outcome(name.removeprefix("run."), event)):
                    return outcome
        return None
