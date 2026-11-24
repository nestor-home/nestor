"""Test doubles and contract suites for the executor port."""

import asyncio
import contextlib
from dataclasses import dataclass, field

from nestor.core import Capabilities, ProviderError, new_id
from nestor.modules.cognition.delegation import (
    CONTINUE,
    RESUME,
    STEER,
    Assignment,
    Executor,
    Outcome,
    Progress,
    RemoteExecutor,
    TurnStatus,
)


class ScriptedExecutor(Executor):
    """Ends each turn after `duration_s` with a report, an error, or a question (`asks`, once per session); keeps a
    session per task, takes instructions while a turn works, confirms a stop unless told otherwise. What it was given
    and steered with is kept to look at."""

    name = "scripted-executor"
    description = "carry out scripted test tasks"
    capabilities = Capabilities.of(CONTINUE, STEER)

    def __init__(
        self,
        result: str = "done",
        *,
        duration_s: float = 0.0,
        error: str | None = None,
        asks: str | None = None,
        confirms_stop: bool = True,
        sensitive: bool = False,
    ):
        self._result, self._duration_s, self._error, self._asks = result, duration_s, error, asks
        self._confirms_stop = confirms_stop
        self.sensitive = sensitive
        self.assignments: list[Assignment] = []  # what it was given, capability and access included
        self.steered: list[tuple[str, str]] = []  # (session, instruction) taken while a turn worked
        self.stopped = 0
        self._working: dict[str, asyncio.Event] = {}  # by session: set to end the turn now
        self._asked: set[str] = set()  # sessions it asked its question in

    @property
    def instructions(self) -> list[str]:
        return [a.instruction for a in self.assignments]

    def finish(self) -> None:
        """End every turn that works now."""
        for done in self._working.values():
            done.set()

    async def run(self, assignment: Assignment, progress: Progress) -> Outcome:
        self.assignments.append(assignment)
        session = assignment.session or new_id()[:8]
        done = self._working[session] = asyncio.Event()
        progress.attach(session)
        progress("started")
        try:
            with contextlib.suppress(TimeoutError):  # a turn that ran its course
                async with asyncio.timeout(self._duration_s):
                    await done.wait()
        except asyncio.CancelledError:
            self.stopped += 1
            return Outcome.stopped(session=session) if self._confirms_stop else Outcome.failed("stop not confirmed")
        finally:
            self._working.pop(session, None)
        if self._error:
            return Outcome.failed(self._error, session=session)
        if self._asks and session not in self._asked:
            self._asked.add(session)
            return Outcome.asked(self._asks, "halfway", session=session)
        return Outcome.completed(self._result, session=session)

    async def steer(self, handle: str, instruction: str) -> bool:
        if handle not in self._working:
            return False
        self.steered.append((handle, instruction))
        return True


class ExecutorContract:
    """Behaviour every `Executor` adapter must show. Implement `executor()`, `slow_executor()`, `failing_executor()`
    and `asking_executor()`; an executor with `CONTINUE` or `STEER` is held to them too."""

    stop_timeout_s = 20.0

    def executor(self) -> Executor:
        raise NotImplementedError

    def slow_executor(self) -> Executor:
        """An executor whose turn runs long enough to be stopped or steered midway."""
        raise NotImplementedError

    def failing_executor(self) -> Executor:
        """An executor whose turn fails (remote error, refused instruction…)."""
        raise NotImplementedError

    def asking_executor(self) -> Executor:
        """An executor whose turn ends on a question for the task's owner."""
        raise NotImplementedError

    def instruction(self) -> str:
        return "Dis bonjour."

    async def test_completes_with_a_report(self) -> None:
        async with self.executor() as executor:
            outcome = await executor.run(Assignment(self.instruction()), Progress())
        assert outcome.status is TurnStatus.COMPLETED, outcome
        assert outcome.result

    async def test_failure_is_returned_not_raised(self) -> None:
        async with self.failing_executor() as executor:
            outcome = await executor.run(Assignment(self.instruction()), Progress())
        assert outcome.status is TurnStatus.FAILED and outcome.error, outcome

    async def test_a_turn_that_needs_its_owner_ends_on_their_question(self) -> None:
        async with self.asking_executor() as executor:
            outcome = await executor.run(Assignment(self.instruction()), Progress())
        assert outcome.status is TurnStatus.ASKED and outcome.question, outcome

    async def test_a_turn_given_its_session_goes_on_in_it(self) -> None:
        async with self.executor() as executor:
            if CONTINUE not in executor.capabilities:
                return
            first = await executor.run(Assignment(self.instruction()), Progress())
            assert first.session, f"an executor that continues names its session: {first}"
            then = await executor.run(Assignment("Et ensuite ?", session=first.session), Progress())
        assert then.status is TurnStatus.COMPLETED and then.session == first.session, (first, then)

    async def test_an_instruction_reaches_the_turn_while_it_works(self) -> None:
        async with self.slow_executor() as executor:
            if STEER not in executor.capabilities:
                return
            handles: list[str] = []
            job = asyncio.create_task(executor.run(Assignment(self.instruction()), Progress(on_attach=handles.append)))
            for _ in range(500):
                if handles:
                    break
                await asyncio.sleep(0.01)
            assert handles, "a turn that can be steered attaches its handle"
            assert await executor.steer(handles[-1], "Fais-le plus court.")
            job.cancel()
            await asyncio.wait({job}, timeout=self.stop_timeout_s)

    async def test_stopping_ends_without_hanging(self) -> None:
        async with self.slow_executor() as executor:
            job = asyncio.create_task(executor.run(Assignment(self.instruction()), Progress()))
            await asyncio.sleep(0.05)
            job.cancel()
            # `wait`, not `wait_for`: a stubborn executor must fail the suite, not hang it.
            done, _ = await asyncio.wait({job}, timeout=self.stop_timeout_s)
            assert done, f"executor still running {self.stop_timeout_s}s after it was stopped"
            if job.cancelled():
                return  # nothing remote was started: local cancellation is enough
            outcome = job.result()
        assert outcome.status in (TurnStatus.STOPPED, TurnStatus.FAILED), outcome


@dataclass(slots=True)
class RemoteRun:
    assignment: Assignment  # what it was given, capability and access included
    session: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    outcome: Outcome | None = None
    follows: int = 0
    steered: list[str] = field(default_factory=list)


class FakeRemote:
    """The remote service behind `ScriptedRemoteExecutor`. Share one between executor instances to play a Nestor
    restart: the turns live on."""

    def __init__(self) -> None:
        self.runs: dict[str, RemoteRun] = {}

    def finish(self, ref: str, outcome: Outcome) -> None:
        run = self.runs[ref]
        if run.outcome is None:
            run.outcome = outcome
            run.done.set()


class ScriptedRemoteExecutor(RemoteExecutor):
    """Remote turns that complete after `duration_s` (never, if `None`: finish them with `remote.finish`), in a session
    per task, taking instructions while they work."""

    name = "scripted-remote"
    description = "carry out scripted remote tasks"
    capabilities = Capabilities.of(RESUME, CONTINUE, STEER)

    def __init__(
        self,
        remote: FakeRemote | None = None,
        *,
        result: str = "done",
        duration_s: float | None = 0.0,
        refuses: bool = False,
        confirms_stop: bool = True,
        asks: str | None = None,
    ) -> None:
        self.remote = remote or FakeRemote()
        self._result, self._duration_s, self._asks = result, duration_s, asks
        self._refuses, self._confirms_stop = refuses, confirms_stop
        self._timers: set[asyncio.Task[None]] = set()

    async def submit(self, assignment: Assignment) -> str:
        if self._refuses:
            raise ProviderError(self.name, "instruction refused", transient=False)
        ref = new_id()[:8]
        self.remote.runs[ref] = RemoteRun(assignment, assignment.session or new_id()[:8])
        if self._duration_s is not None:
            timer = asyncio.create_task(self._complete(ref, self._duration_s))
            self._timers.add(timer)
            timer.add_done_callback(self._timers.discard)
        return ref

    async def follow(self, ref: str, progress: Progress) -> Outcome:
        run = self.remote.runs[ref]
        run.follows += 1
        progress("working")
        await run.done.wait()
        assert run.outcome is not None
        return run.outcome

    async def stop(self, ref: str) -> bool:
        if self._confirms_stop:
            self.remote.finish(ref, Outcome.stopped(session=self.remote.runs[ref].session))
        return self._confirms_stop

    def session_of(self, ref: str) -> str | None:
        run = self.remote.runs.get(ref)
        return run.session if run else None

    async def steer(self, handle: str, instruction: str) -> bool:
        run = self.remote.runs.get(handle)
        if run is None or run.outcome is not None:
            return False
        run.steered.append(instruction)
        return True

    async def _complete(self, ref: str, after_s: float) -> None:
        await asyncio.sleep(after_s)
        run = self.remote.runs[ref]
        if self._asks:
            self.remote.finish(ref, Outcome.asked(self._asks, session=run.session))
        else:
            self.remote.finish(ref, Outcome.completed(self._result, session=run.session))


class RemoteExecutorContract(ExecutorContract):
    """What a `RemoteExecutor` adds to the executor contract: its turns can be followed again."""

    def executor(self) -> RemoteExecutor:
        raise NotImplementedError

    async def test_a_turn_can_be_followed_again_without_starting_twice(self) -> None:
        async with self.executor() as executor:
            ref = await executor.submit(Assignment(self.instruction()))
            first = await executor.follow(ref, Progress())
        async with self.executor() as restarted:
            again = await restarted.follow(ref, Progress())
        assert first == again and first.status is TurnStatus.COMPLETED, (first, again)
