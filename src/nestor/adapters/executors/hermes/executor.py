"""A Hermes agent profile that runs Nestor's tasks."""

import asyncio
from typing import Any

import httpx

from nestor.adapters.executors.common import INSTRUCTIONS, QUESTION_INSTRUCTIONS, described
from nestor.adapters.executors.hermes.runs import (
    UnexpectedReply,
    clarified,
    decode,
    payload,
    run_outcome,
    run_path,
    run_step,
    waiting_on,
)
from nestor.core import Capabilities, ContractError, ProviderError
from nestor.modules.cognition.delegation import (
    CONTINUE,
    RESUME,
    STEER,
    Assignment,
    NestorAccess,
    NestorTools,
    Outcome,
    Progress,
    RemoteExecutor,
)

PROFILE = """mcp_servers:
  nestor:
    url: "{url}"
    headers:
      Authorization: "Bearer {key}"
"""
REPORT_FORMAT = (
    ' Your final answer is only this JSON object: {"report": "…", "question": "…"}. Never use the clarify tool: '
    "ask in `question` instead."
)


class HermesExecutor(RemoteExecutor):
    """Delegates objectives to a Hermes agent profile; its runs outlive Nestor.

    `description` states what this Hermes profile's tools really allow: the assistant promises
    exactly that. Stream reads have no timeout (a run may take minutes); connections and plain
    requests time out after `timeout_s`.
    """

    name = "hermes"
    brand = "hermes"
    capabilities = Capabilities.of(RESUME, CONTINUE, STEER)

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
        nestor_mcp: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`nestor_mcp`: its profile declares Nestor's MCP server, as `nestor`, with this executor's key."""
        self.description = description
        self.nestor_tools = NestorTools.CONFIGURED if nestor_mcp else NestorTools.NONE
        self._base_url, self._api_key, self._model = base_url, api_key, model
        self._instructions = instructions + QUESTION_INSTRUCTIONS + REPORT_FORMAT
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

    def setup(self, access: NestorAccess) -> str:
        """The `mcp_servers` entry of the Hermes profile's `config.yaml`."""
        return PROFILE.format(url=access.url, key=access.key)

    async def submit(self, assignment: Assignment) -> str:
        body: dict[str, Any] = {"model": self._model, "input": assignment.brief(), "instructions": self._instructions}
        if assignment.session is not None:
            body["session_id"] = assignment.session  # Hermes loads that session's history into the run
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
        session: str | None = None
        try:
            state = await self._state(ref)
            session = state.get("session_id") if isinstance(state.get("session_id"), str) else None
            outcome = (
                await self._settled(ref, state, session)
                or await self._stream(ref, progress, session)
                or await self._settled(ref, await self._state(ref), session)
            )
        except httpx.HTTPError as error:
            return Outcome.failed(f"lost contact with Hermes: {described(error)}", session=session)
        except UnexpectedReply as error:
            return Outcome.failed(f"unexpected reply from Hermes: {error}", session=session)
        return outcome or Outcome.failed("Hermes event stream ended before the run finished", session=session)

    async def stop(self, ref: str) -> bool:
        try:
            async with asyncio.timeout(self._stop_timeout_s):
                payload(await self._http.post(f"{run_path(ref)}/stop"))
                while True:
                    status = (await self._state(ref)).get("status")
                    if status == "cancelled":
                        return True
                    if status in ("completed", "failed", "interrupted"):
                        return False  # finished on its own before the stop
                    await asyncio.sleep(self._poll_interval_s)
        except (TimeoutError, httpx.HTTPError, UnexpectedReply):
            return False

    async def steer(self, handle: str, instruction: str) -> bool:
        """Hermes delivers it after the run's current tool calls; one it could not deliver before the run ended comes
        back as `pending_steer`, said in the outcome."""
        try:
            payload(await self._http.post(f"{run_path(handle)}/steer", json={"input": instruction}))
        except (httpx.HTTPError, UnexpectedReply):
            return False  # 409 when the run is not running or did not take it, 404 for a run it does not know
        return True

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ContractError(f"{self.name} executor used before start()")
        return self._client

    async def _state(self, ref: str) -> dict[str, Any]:
        return payload(await self._http.get(run_path(ref)))

    async def _settled(self, ref: str, state: dict[str, Any], session: str | None) -> Outcome | None:
        """The run's outcome if it is over or waits on its owner, `None` while it works."""
        if question := waiting_on(state):
            return await self._asked(ref, question, session)
        return run_outcome(str(state.get("status")), state, session)

    async def _asked(self, ref: str, question: str, session: str | None) -> Outcome:
        """A run that asked with `clarify` would hold a Hermes worker until its answer, or until Hermes gives up: the
        turn ends on its question instead, and the answer comes as the next turn, in the same session."""
        await self.stop(ref)
        return Outcome.asked(question, session=session)

    async def _stream(self, ref: str, progress: Progress, session: str | None) -> Outcome | None:
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
                elif name == "clarify.request" and (question := clarified(event)):
                    return await self._asked(ref, question, session)
                elif name.startswith("run.") and (outcome := run_outcome(name.removeprefix("run."), event, session)):
                    return outcome
        return None
