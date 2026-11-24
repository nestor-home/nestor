"""Hermes executor: the remote executor contract against a fake Hermes Runs API, then what only
an HTTP service can break (refusals, dropped streams, unconfirmed stops)."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from nestor.adapters.executors.hermes import HermesExecutor, HermesSettings, plugin
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.cognition.delegation import Assignment, NestorAccess, NestorTools, Progress, TurnStatus
from nestor.runtime import Services
from nestor.testing.cognition import RemoteExecutorContract
from nestor.testing.i18n import EchoLocalizer

BASE_URL = "https://hermes.test/v1"
API_KEY = "test-key"


@dataclass(slots=True)
class FakeRun:
    body: dict[str, Any]
    session: str
    status: str = "queued"
    output: str = ""
    error: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)
    steered: list[str] = field(default_factory=list)
    controls: list[dict[str, Any]] = field(default_factory=list)  # prompts it waits on (`clarify`)
    changed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def objective(self) -> str:
        return self.body["input"]


class FakeHermes:
    """Plays the Hermes Runs API as read in its code and observed on the real server: run state with its session,
    replayed SSE events, steer and stop requests. Runs finish immediately unless `holds` (then the test finishes
    them); one that `asks` ends on a JSON report with that question, as its instructions ask."""

    def __init__(
        self, *, holds: bool = False, confirms_stop: bool = True, refuses: int | None = None, asks: str | None = None
    ) -> None:
        self.holds, self.confirms_stop, self.refuses, self.asks = holds, confirms_stop, refuses, asks
        self.runs: dict[str, FakeRun] = {}
        self.drops_stream = False
        self.finishes_on_drop: str | None = None  # the run completes, unseen, as its stream drops
        self.broken_line: str | None = None
        self.state_error: int | None = None
        self.transport = httpx.MockTransport(self.handle)

    def executor(self, **options: Any) -> HermesExecutor:
        options.setdefault("description", "search the web")
        options.setdefault("poll_interval_s", 0.01)
        return HermesExecutor(BASE_URL, API_KEY, "Richie", transport=self.transport, **options)

    def emit(self, ref: str, event: str, **fields: Any) -> None:
        run = self.runs[ref]
        run.events.append({"event": event, "run_id": ref, **fields})
        if event.startswith("run."):
            run.status = event.removeprefix("run.")
            run.output = fields.get("output", run.output)
            run.error = fields.get("error")
        run.changed.set()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != f"Bearer {API_KEY}":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        parts = request.url.path.removeprefix("/v1/").split("/")
        if parts == ["runs"]:
            return self._submit(json.loads(request.content))
        run = self.runs.get(parts[1])
        if run is None:
            return httpx.Response(404, json={"error": {"message": f"Run not found: {parts[1]}"}})
        match parts[2:]:
            case ["events"]:
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=self._events(run))
            case ["stop"]:
                if self.confirms_stop and run.status in ("queued", "running"):
                    self.emit(parts[1], "run.cancelled")
                return httpx.Response(200, json={"run_id": parts[1], "status": "stopping"})
            case ["steer"]:
                if run.status != "running":
                    return httpx.Response(409, json={"error": {"code": "run_not_accepting_steer"}})
                run.steered.append(json.loads(request.content)["input"])
                return httpx.Response(200, json={"object": "hermes.run.steer", "run_id": parts[1], "accepted": True})
            case _:
                if self.state_error:
                    return httpx.Response(self.state_error, text="boom")
                state = {"run_id": parts[1], "status": run.status, "session_id": run.session}
                state["pending_controls"] = run.controls
                return httpx.Response(200, json={**state, "output": run.output, "error": run.error})

    def _submit(self, body: dict[str, Any]) -> httpx.Response:
        if self.refuses:
            return httpx.Response(self.refuses, json={"error": {"message": "refused"}})
        ref = f"run_{len(self.runs)}"
        self.runs[ref] = FakeRun(body, body.get("session_id") or ref)  # a new session is named after its first run
        if self.holds:
            self.runs[ref].status = "running"
        else:
            self.emit(ref, "tool.started", tool="web_search", preview="weather Paris")
            output = json.dumps({"report": "halfway", "question": self.asks}) if self.asks else f"done: {body['input']}"
            self.emit(ref, "run.completed", output=output)
        return httpx.Response(202, json={"run_id": ref, "status": "started"})

    async def _events(self, run: FakeRun) -> AsyncIterator[bytes]:
        yield b": open\n\n"
        sent = 0
        while True:
            for event in run.events[sent:]:
                yield f"id: {sent}\ndata: {json.dumps(event)}\n\n".encode()
                sent += 1
                if event["event"] in ("run.completed", "run.failed", "run.cancelled"):
                    return
            if self.broken_line:
                yield self.broken_line.encode()
            if self.drops_stream:
                if self.finishes_on_drop:
                    run.status, run.output = "completed", self.finishes_on_drop
                return
            run.changed.clear()
            await run.changed.wait()


class TestHermesExecutor(RemoteExecutorContract):
    stop_timeout_s = 2.0

    @pytest.fixture(autouse=True)
    def _server(self) -> None:
        self.server = FakeHermes()

    def executor(self) -> HermesExecutor:
        return self.server.executor()

    def slow_executor(self) -> HermesExecutor:
        return FakeHermes(holds=True).executor()

    def failing_executor(self) -> HermesExecutor:
        return FakeHermes(refuses=400).executor()

    def asking_executor(self) -> HermesExecutor:
        return FakeHermes(asks="Quel budget ?").executor()


async def test_a_new_executor_follows_a_run_still_going_to_its_end() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Résume les actualités."))
    async with server.executor() as restarted:
        following = asyncio.create_task(restarted.follow(ref, Progress()))
        await asyncio.sleep(0.01)
        server.emit(ref, "run.completed", output="trois titres")
        outcome = await asyncio.wait_for(following, 1)
    assert outcome.status is TurnStatus.COMPLETED and outcome.result == "trois titres"


async def test_tool_calls_are_reported_as_progress_steps_without_commands_or_code() -> None:
    server = FakeHermes(holds=True)
    steps: list[str] = []
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Quel temps fait-il ?"))
        following = asyncio.create_task(executor.follow(ref, Progress(steps.append)))
        await asyncio.sleep(0.01)
        server.emit(ref, "tool.started", tool="web_search", preview="météo Paris")
        server.emit(ref, "tool.started", tool="terminal", preview="curl -s wttr.in/Paris | tee ~/.secret")
        server.emit(ref, "tool.started", tool="browser")
        server.emit(ref, "message.delta", delta="Il fait")
        server.emit(ref, "run.completed", output="Il fait beau.")
        await asyncio.wait_for(following, 1)
    assert steps == ["web_search: météo Paris", "terminal", "browser"]


async def test_the_first_turn_starts_a_session_with_the_profile_and_instructions() -> None:
    server = FakeHermes()
    async with server.executor(instructions="Be brief.") as executor:
        ref = await executor.submit(Assignment("Allume la lampe."))
        outcome = await executor.follow(ref, Progress())
    body = server.runs[ref].body
    assert body["model"] == "Richie" and body["input"].startswith("Allume la lampe.") and "session_id" not in body
    assert body["instructions"].startswith("Be brief.") and '"question"' in body["instructions"]
    assert outcome.session == ref  # Hermes names a new session after its first run


async def test_a_turn_given_its_session_goes_on_in_that_hermes_session() -> None:
    server = FakeHermes()
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Et pour mardi ?", session="run_earlier"))
        outcome = await executor.follow(ref, Progress())
    assert server.runs[ref].body["session_id"] == "run_earlier"
    assert outcome.status is TurnStatus.COMPLETED and outcome.session == "run_earlier"


async def test_an_instruction_is_steered_into_a_running_run_and_refused_once_it_ended() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        assert await executor.steer(ref, "Plutôt le matin.")
        server.emit(ref, "run.completed", output="Vol de 8 h trouvé.")
        assert not await executor.steer(ref, "Et en train ?")
        assert not await executor.steer("run_missing", "Et en train ?")
    assert server.runs[ref].steered == ["Plutôt le matin."]


async def test_an_instruction_hermes_could_not_deliver_is_said_in_the_outcome() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        following = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.01)
        server.emit(ref, "run.completed", output="Vol de 8 h trouvé.", pending_steer="Plutôt le soir.")
        outcome = await asyncio.wait_for(following, 1)
    assert outcome.status is TurnStatus.COMPLETED
    assert "Vol de 8 h trouvé." in (outcome.result or "") and "Plutôt le soir." in (outcome.result or "")


@pytest.mark.parametrize(
    "output",
    [
        '{"report": "Deux vols.", "question": "Lequel ?"}',
        'Voici mon rapport.\n```json\n{"report": "Deux vols.", "question": "Lequel ?"}\n```',
    ],
)
async def test_a_report_ending_on_a_question_ends_the_turn_on_it(output: str) -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        server.emit(ref, "run.completed", output=output)
        outcome = await executor.follow(ref, Progress())
    assert outcome.status is TurnStatus.ASKED and outcome.question == "Lequel ?" and outcome.result == "Deux vols."
    assert outcome.session == ref


async def test_a_run_that_asks_with_clarify_is_stopped_and_ends_on_its_question() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Réserve une table."))
        following = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.01)
        server.emit(ref, "clarify.request", kind="clarify", question="Quel soir ?", choices=["vendredi", "samedi"])
        outcome = await asyncio.wait_for(following, 1)
    assert outcome.status is TurnStatus.ASKED and outcome.session == ref
    assert "Quel soir ?" in (outcome.question or "") and "samedi" in (outcome.question or "")
    assert server.runs[ref].status == "cancelled"  # no Hermes worker left waiting on the person


async def test_a_run_found_waiting_on_clarify_after_a_restart_ends_on_its_question() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Réserve une table."))
    server.runs[ref].controls.append({"kind": "clarify", "prompt_id": "c1", "question": "Pour combien ?"})
    async with server.executor() as restarted:
        outcome = await asyncio.wait_for(restarted.follow(ref, Progress()), 1)
    assert outcome.status is TurnStatus.ASKED and outcome.question == "Pour combien ?"
    assert server.runs[ref].status == "cancelled"


async def test_a_profile_with_nestor_s_tools_gets_the_task_s_capability_in_its_objective() -> None:
    server = FakeHermes()
    async with server.executor(nestor_mcp=True) as reaching, server.executor() as plain:
        assert (reaching.nestor_tools, plain.nestor_tools) == (NestorTools.CONFIGURED, NestorTools.NONE)
        ref = await reaching.submit(Assignment("Cherche un vol.", task="nstt_task"))
    assert server.runs[ref].objective.startswith("Cherche un vol.") and 'task="nstt_task"' in server.runs[ref].objective
    entry = reaching.setup(NestorAccess(url="https://nestor.example/mcp", key="nstx_k"))
    assert 'url: "https://nestor.example/mcp"' in entry and 'Authorization: "Bearer nstx_k"' in entry


@pytest.mark.parametrize(("status", "transient"), [(400, False), (401, False), (429, True), (503, True)])
async def test_a_refused_submission_raises_a_provider_error(status: int, transient: bool) -> None:
    async with FakeHermes(refuses=status).executor() as executor:
        with pytest.raises(ProviderError) as raised:
            await executor.submit(Assignment("Fais quelque chose."))
    assert raised.value.transient is transient


async def test_an_unreachable_server_is_a_transient_provider_error() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    executor = HermesExecutor(BASE_URL, API_KEY, "Richie", description="", transport=httpx.MockTransport(unreachable))
    async with executor:
        with pytest.raises(ProviderError) as raised:
            await executor.submit(Assignment("Fais quelque chose."))
    assert raised.value.transient


@pytest.mark.parametrize("reply", [b"<html>proxy</html>", b"[]", b'{"status": "started"}'])
async def test_a_submission_reply_without_a_run_id_is_a_provider_error(reply: bytes) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(202, content=reply))
    async with HermesExecutor(BASE_URL, API_KEY, "Richie", description="", transport=transport) as executor:
        with pytest.raises(ProviderError):
            await executor.submit(Assignment("Fais quelque chose."))


@pytest.mark.parametrize("error", ["quota exceeded", {"message": "quota exceeded"}])
async def test_a_failed_run_returns_its_error(error: Any) -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Commande des pizzas."))
        following = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.01)
        server.emit(ref, "run.failed", error=error)
        outcome = await asyncio.wait_for(following, 1)
    assert outcome.status is TurnStatus.FAILED and outcome.error == "quota exceeded"


@pytest.mark.parametrize("ended", ["run.failed", "run.interrupted"])
async def test_a_run_that_already_failed_is_reported_failed_after_a_restart(ended: str) -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Commande des pizzas."))
        server.emit(ref, ended)
    async with server.executor() as restarted:
        outcome = await asyncio.wait_for(restarted.follow(ref, Progress()), 1)
    assert outcome.status is TurnStatus.FAILED and outcome.error


async def test_a_run_stopped_elsewhere_is_reported_stopped() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        following = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.01)
        server.emit(ref, "run.cancelled")
        outcome = await asyncio.wait_for(following, 1)
    assert outcome.status is TurnStatus.STOPPED


async def test_a_dropped_stream_is_a_failure_while_the_run_goes_on() -> None:
    server = FakeHermes(holds=True)
    server.drops_stream = True
    async with server.executor() as executor:
        outcome = await executor.follow(await executor.submit(Assignment("Cherche un vol.")), Progress())
    assert outcome.status is TurnStatus.FAILED and "stream ended" in (outcome.error or "")


async def test_a_run_that_finished_as_the_stream_dropped_returns_its_result() -> None:
    server = FakeHermes(holds=True)
    server.drops_stream, server.finishes_on_drop = True, "vol trouvé"
    async with server.executor() as executor:
        outcome = await executor.follow(await executor.submit(Assignment("Cherche un vol.")), Progress())
    assert outcome.status is TurnStatus.COMPLETED and outcome.result == "vol trouvé"


async def test_a_garbled_event_is_a_failure_not_an_exception() -> None:
    server = FakeHermes(holds=True)
    server.broken_line = "data: {not json\n\n"
    async with server.executor() as executor:
        outcome = await executor.follow(await executor.submit(Assignment("Cherche un vol.")), Progress())
    assert outcome.status is TurnStatus.FAILED and "unexpected reply" in (outcome.error or "")


async def test_following_an_unknown_run_is_a_failure() -> None:
    async with FakeHermes().executor() as executor:
        outcome = await executor.follow("run_missing", Progress())
    assert outcome.status is TurnStatus.FAILED and "404" in (outcome.error or "")


async def test_an_events_endpoint_error_is_a_failure() -> None:
    server = FakeHermes(holds=True)

    async def no_events(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events"):
            return httpx.Response(502, text="bad gateway")
        return await server.handle(request)

    async with HermesExecutor(
        BASE_URL, API_KEY, "Richie", description="", transport=httpx.MockTransport(no_events)
    ) as e:
        outcome = await e.follow(await e.submit(Assignment("Cherche un vol.")), Progress())
    assert outcome.status is TurnStatus.FAILED and "502" in (outcome.error or "")


async def test_losing_the_server_while_following_is_a_failure() -> None:
    server = FakeHermes(holds=True)

    async def gone(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            raise httpx.ReadError("connection reset", request=request)
        return await server.handle(request)

    async with HermesExecutor(BASE_URL, API_KEY, "Richie", description="", transport=httpx.MockTransport(gone)) as e:
        outcome = await e.follow(await e.submit(Assignment("Cherche un vol.")), Progress())
    assert outcome.status is TurnStatus.FAILED and "lost contact" in (outcome.error or "")


async def test_a_confirmed_stop_returns_true() -> None:
    server = FakeHermes(holds=True)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        assert await executor.stop(ref)
    assert server.runs[ref].status == "cancelled"


async def test_an_unconfirmed_stop_returns_false_after_the_timeout() -> None:
    server = FakeHermes(holds=True, confirms_stop=False)
    async with server.executor(stop_timeout_s=0.05) as executor:
        assert not await asyncio.wait_for(executor.stop(await executor.submit(Assignment("Cherche un vol."))), 1)


async def test_stopping_a_run_that_already_finished_returns_false() -> None:
    async with FakeHermes().executor() as executor:
        assert not await executor.stop(await executor.submit(Assignment("Dis bonjour.")))


async def test_stopping_an_unknown_run_returns_false() -> None:
    async with FakeHermes().executor() as executor:
        assert not await executor.stop("run_missing")


async def test_a_stop_whose_state_cannot_be_read_returns_false() -> None:
    server = FakeHermes(holds=True, confirms_stop=False)
    async with server.executor() as executor:
        ref = await executor.submit(Assignment("Cherche un vol."))
        server.state_error = 500
        assert not await executor.stop(ref)


async def test_using_the_executor_before_start_fails_clearly() -> None:
    with pytest.raises(ContractError, match="before start"):
        await FakeHermes().executor().submit(Assignment("Dis bonjour."))


async def test_close_can_be_called_twice() -> None:
    executor = FakeHermes().executor()
    await executor.start()
    await executor.start()
    await executor.close()
    await executor.close()
    with pytest.raises(ContractError):
        await executor.submit(Assignment("Dis bonjour."))


async def test_the_plugin_builds_an_executor_described_by_its_configuration(tmp_path: Any) -> None:
    raw = {"base_url": BASE_URL, "api_key": API_KEY, "model": "Richie", "description": "search the web"}
    executor = plugin.create(
        raw, "hermes", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    )
    assert isinstance(executor, HermesExecutor) and executor.description == "search the web"
    assert API_KEY not in repr(HermesSettings.model_validate(raw))


@pytest.mark.live
async def test_live_a_run_completes_and_can_be_followed_again() -> None:
    names = ("HERMES_BASE_URL", "HERMES_API_KEY", "HERMES_MODEL")
    if not all(os.environ.get(n) for n in names):
        pytest.skip("Hermes is not configured (HERMES_BASE_URL, HERMES_API_KEY, HERMES_MODEL)")
    base_url, api_key, model = (os.environ[n] for n in names)
    async with HermesExecutor(base_url, api_key, model, description="") as executor:
        ref = await executor.submit(Assignment("Réponds juste OK, sans utiliser d'outil."))
        outcome = await asyncio.wait_for(executor.follow(ref, Progress()), 120)
    async with HermesExecutor(base_url, api_key, model, description="") as restarted:
        again = await asyncio.wait_for(restarted.follow(ref, Progress()), 30)
    assert outcome.status is TurnStatus.COMPLETED and "OK" in (outcome.result or ""), outcome
    assert again == outcome
