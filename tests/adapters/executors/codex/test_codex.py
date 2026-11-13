"""Codex executor: the remote executor contract against a fake `codex app-server` reached through a relay, as on a
server, then what only this protocol can break (sessions that end, approvals, files handed back, stops)."""

import asyncio
import json
import os
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from nestor.adapters.executors.codex import CodexSettings, Sandbox, build
from nestor.adapters.executors.common import MAX_FILES
from nestor.core import ContractError, Health, ProviderError
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import Progress, TaskStatus
from nestor.runtime import Services
from nestor.testing.cognition import RemoteExecutorContract
from nestor.testing.i18n import EchoLocalizer

from .fakes import CWD, FakeCodex


class TestCodexExecutor(RemoteExecutorContract):
    @pytest.fixture(autouse=True)
    async def served(self) -> AsyncIterator[None]:
        async with FakeCodex() as self.codex, FakeCodex(holds=True) as self.held, FakeCodex(fails=True) as self.failing:
            yield

    def executor(self) -> Any:
        return self.codex.executor()

    def slow_executor(self) -> Any:
        return self.held.executor()

    def failing_executor(self) -> Any:
        return self.failing.executor()


async def submitted(codex: FakeCodex, **options: Any) -> tuple[Any, str]:
    executor = codex.executor(**options)
    await executor.start()
    return executor, await executor.submit("Corrige le test.")


async def test_the_task_runs_where_and_how_the_configuration_says() -> None:
    async with FakeCodex() as codex:
        options = {
            "model": "gpt-6.1",
            "sandbox": Sandbox.READ_ONLY,
            "config": {"mcp_servers": {}},
            "instructions": "Sois bref.",
        }
        async with codex.executor(**options) as executor:
            await executor.run("Corrige le test.", Progress())
    [started] = [params for method, params in codex.requests if method == "thread/start"]
    assert {k: started[k] for k in ("cwd", "sandbox", "approvalPolicy", "model", "config")} == {
        "cwd": CWD,
        "sandbox": "read-only",
        "approvalPolicy": "never",
        "model": "gpt-6.1",
        "config": {"mcp_servers": {}},
    }
    assert started["developerInstructions"].startswith("Sois bref.") and "`files`" in started["developerInstructions"]
    [turn] = [params for method, params in codex.requests if method == "turn/start"]
    assert turn["input"] == [{"type": "text", "text": "Corrige le test."}]
    assert turn["outputSchema"]["required"] == ["report", "files"]


async def test_the_report_is_the_final_answer_and_the_turns_items_are_progress() -> None:
    steps: list[str] = []
    async with FakeCodex() as codex, codex.executor() as executor:
        outcome = await executor.run("Corrige le test.", Progress(steps.append))
    assert outcome.result == "C'est fait." and outcome.files == ()
    assert steps == [
        "command: /bin/bash -lc 'ls'",
        "editing: src/a.py",
        "nestor: read_result",
        "web search: pytest asyncio",
        "drawing an image",
    ]


async def test_a_final_answer_that_is_not_a_structured_report_is_the_report() -> None:
    async with FakeCodex(report="Tout est vert.") as codex, codex.executor() as executor:
        outcome = await executor.run("Lance les tests.", Progress())
    assert outcome.status is TaskStatus.COMPLETED and outcome.result == "Tout est vert."


async def test_the_files_the_report_lists_come_back_from_the_working_directory_only() -> None:
    pdf = b"%PDF-1.7 devis"
    files = {f"{CWD}/devis.pdf": pdf, f"{CWD}/big.bin": b"x" * 2_000, "/etc/passwd": b"root:x:0:0"}
    listed = [
        "devis.pdf",
        f"{CWD}/big.bin",
        "/etc/passwd",
        f"{CWD}/../../etc/passwd",
        f"{CWD}/missing.txt",
        CWD + "/sub",
    ]
    files[f"{CWD}/sub/inner.txt"] = b"inner"
    files["/srv/codex/.codex/auth.json"] = b'{"token": "secret"}'
    links = {f"{CWD}/auth.json": "/srv/codex/.codex/auth.json", f"{CWD}/home": "/srv/codex/.codex"}
    files[f"{CWD}/locked.txt"] = b"mine"
    listed += ["auth.json", "home/auth.json", "locked.txt"]
    codex = FakeCodex(files=files, links=links, report={"report": "Devis écrit.", "files": listed})
    async with codex, codex.executor(max_file_bytes=1_000) as executor:
        outcome = await executor.run("Écris le devis.", Progress())
    [devis] = outcome.files
    assert (devis.name, devis.kind, devis.media_type, devis.data) == (
        "devis.pdf",
        AttachmentKind.FILE,
        "application/pdf",
        pdf,
    )
    assert outcome.result is not None and outcome.result.startswith("Devis écrit.\nFiles left out: ")
    for left in (
        "big.bin (larger than 1000 bytes)",
        "/etc/passwd (outside the working directory)",
        "missing.txt (No such",
        "sub (not a file)",
        "auth.json (a link, not followed)",
        "home/auth.json (a link, not followed)",
        "locked.txt (wc: ",
    ):
        assert left in outcome.result, left
    read = [params["path"] for method, params in codex.requests if method == "fs/readFile"]
    assert read == [f"{CWD}/devis.pdf"], "nothing too large or outside is downloaded, not even through a link"


async def test_no_more_files_than_the_limit_come_back() -> None:
    files = {f"{CWD}/{n}.txt": b"x" for n in range(MAX_FILES + 2)}
    codex = FakeCodex(files=files, report={"report": "Faits.", "files": list(files)})
    async with codex, codex.executor() as executor:
        outcome = await executor.run("Écris-les.", Progress())
    assert len(outcome.files) == MAX_FILES and f"(more than {MAX_FILES} files)" in (outcome.result or "")


async def test_a_turn_still_running_is_followed_to_its_end_after_a_restart() -> None:
    async with FakeCodex(holds=True) as codex:
        first, ref = await submitted(codex)
        await first.close()  # Nestor stops; the daemon goes on
        async with codex.executor() as restarted:
            follow = asyncio.create_task(restarted.follow(ref, Progress()))
            await asyncio.sleep(0.3)
            await codex.finish(ref, report={"report": "Réparé.", "files": []})
            outcome = await asyncio.wait_for(follow, 5)
    assert outcome.result == "Réparé." and [m for m, _ in codex.requests].count("turn/start") == 1


async def test_a_turn_a_local_server_took_down_with_it_is_reported_cut_short() -> None:
    async with FakeCodex(holds=True, daemon=False) as codex:
        first, ref = await submitted(codex)
        await first.close()
        async with codex.executor() as restarted:
            outcome = await restarted.follow(ref, Progress())
    assert outcome.status is TaskStatus.FAILED and "stopped before it ended" in (outcome.error or "")


async def test_a_turn_that_failed_or_was_stopped_elsewhere_says_so_after_a_restart() -> None:
    async with FakeCodex(fails=True) as codex:
        _, ref = await submitted(codex)
        await asyncio.sleep(0.2)
        async with codex.executor() as restarted:
            outcome = await restarted.follow(ref, Progress())
    assert (outcome.status, outcome.error) == (TaskStatus.FAILED, "the model refused")
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex)
        codex.turn(ref).status = "interrupted"  # someone stopped it from Codex's own interface
        async with codex.executor() as restarted:
            assert (await restarted.follow(ref, Progress())).status is TaskStatus.CANCELLED
        await executor.close()


async def test_a_session_lost_while_the_turn_goes_on_is_opened_again() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex, reconnect_s=(0.1,))
        follow = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.3)
        codex.drop_sessions()  # the relay broke; the daemon still runs the turn
        await asyncio.sleep(0.5)
        await codex.finish(ref, report={"report": "Réparé.", "files": []})
        outcome = await asyncio.wait_for(follow, 5)
        await executor.close()
    assert outcome.result == "Réparé."


async def test_a_codex_gone_for_good_while_following_is_a_failure() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex, reconnect_s=(0.05, 0.05))
        follow = asyncio.create_task(executor.follow(ref, Progress()))
        await asyncio.sleep(0.3)
        codex.go_away()
        outcome = await asyncio.wait_for(follow, 10)
        await executor.close()
    assert outcome.status is TaskStatus.FAILED and "lost contact with Codex" in (outcome.error or "")


async def test_the_end_of_a_turn_is_what_its_notification_says_while_the_history_lags() -> None:
    async with FakeCodex(lags=True) as codex, codex.executor() as executor:
        outcome = await asyncio.wait_for(executor.run("Corrige le test.", Progress()), 5)
    assert outcome.result == "C'est fait."


async def test_a_session_that_never_answers_is_closed_with_its_process(tmp_path: Path) -> None:
    """Whether the answer times out or the submission is cancelled: no half-open session, no process left."""

    def silent(name: str) -> list[str]:
        pid = tmp_path / name
        return [
            sys.executable,
            "-c",
            f"import os, time; open({str(pid)!r}, 'w').write(str(os.getpid())); time.sleep(60)",
        ]

    async with FakeCodex() as codex, codex.executor(command=silent("timed-out"), timeout_s=0.5) as executor:
        with pytest.raises(ProviderError):
            await executor.submit("Corrige le test.")
        assert executor.health() is Health.UNAVAILABLE
    async with FakeCodex() as codex, codex.executor(command=silent("cancelled"), timeout_s=30) as executor:
        submission = asyncio.create_task(executor.submit("Corrige le test."))
        await asyncio.sleep(0.5)
        submission.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submission
    for name in ("timed-out", "cancelled"):
        with pytest.raises(ProcessLookupError):
            os.kill(int((tmp_path / name).read_text()), 0)


@pytest.mark.parametrize(
    ("asks", "answer"),
    [
        ("item/commandExecution/requestApproval", {"result": {"decision": "decline"}}),
        ("item/fileChange/requestApproval", {"result": {"decision": "decline"}}),
        ("execCommandApproval", {"result": {"decision": "denied"}}),
        ("item/tool/requestUserInput", {"result": {"answers": {}}}),
        ("mcpServer/elicitation/request", {"result": {"action": "decline"}}),
        ("item/permissions/requestApproval", {"error": {"code": -32601}}),
    ],
)
async def test_a_request_for_approval_or_input_is_declined(asks: str, answer: dict[str, Any]) -> None:
    async with FakeCodex(asks=asks) as codex, codex.executor() as executor:
        outcome = await executor.run("Nettoie le disque.", Progress())
    assert outcome.status is TaskStatus.COMPLETED
    [given] = codex.answers
    key = next(iter(answer))
    assert {key: {k: given[key][k] for k in answer[key]}} == answer


async def test_a_confirmed_stop_returns_true() -> None:
    async with FakeCodex(holds=True) as codex:
        executor, ref = await submitted(codex)
        assert await executor.stop(ref) is True
        await executor.close()
    assert codex.turn(ref).status == "interrupted"


async def test_an_unconfirmed_stop_returns_false_after_the_timeout() -> None:
    async with FakeCodex(holds=True, confirms_stop=False) as codex:
        executor, ref = await submitted(codex, stop_timeout_s=0.3)
        assert await executor.stop(ref) is False
        await executor.close()


async def test_stopping_a_turn_that_already_finished_returns_false() -> None:
    async with FakeCodex() as codex:
        executor, ref = await submitted(codex)
        await executor.follow(ref, Progress())
        assert await executor.stop(ref) is False
        await executor.close()


async def test_stopping_or_following_an_unknown_task_fails_without_raising() -> None:
    async with FakeCodex() as codex, codex.executor() as executor:
        assert await executor.stop("thread-9:turn-9") is False
        unknown = await executor.follow("thread-9:turn-9", Progress())
        garbled = await executor.follow("no-separator", Progress())
    assert unknown.status is TaskStatus.FAILED and "invalid thread id" in (unknown.error or "")
    assert garbled.status is TaskStatus.FAILED


async def test_a_codex_that_cannot_be_reached_is_unavailable() -> None:
    async with (
        FakeCodex() as codex,
        codex.executor(command=["codex-that-is-not-installed", "app-server"], reconnect_s=()) as missing,
    ):
        with pytest.raises(ProviderError) as refused:
            await missing.submit("Corrige le test.")
        outcome = await missing.run("Corrige le test.", Progress())
        followed = await missing.follow("thread-1:turn-2", Progress())
        health = (missing.health(), missing.health_detail())
    assert refused.value.transient and outcome.status is TaskStatus.FAILED and followed.status is TaskStatus.FAILED
    assert health == (Health.UNAVAILABLE, Message.of("health-executor-unreachable", executor="codex"))


async def test_a_reply_outside_the_protocol_or_a_session_that_hangs_up_is_a_provider_error() -> None:
    async with FakeCodex(garbled=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as garbled:
            await executor.submit("Corrige le test.")
        followed = await executor.follow("thread-1:turn-2", Progress())
    async with FakeCodex(hangs_up=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as hung_up:
            await executor.submit("Corrige le test.")
    assert not garbled.value.transient and hung_up.value.transient
    assert followed.status is TaskStatus.FAILED and "unexpected reply" in (followed.error or "")


async def test_a_refused_thread_is_a_provider_error_from_a_codex_that_answers() -> None:
    async with FakeCodex(refuses=True) as codex, codex.executor() as executor:
        with pytest.raises(ProviderError) as refused:
            await executor.submit("Corrige le test.")
        assert not refused.value.transient and executor.health() is Health.STARTED


async def test_using_the_executor_before_start_fails_clearly() -> None:
    async with FakeCodex() as codex:
        with pytest.raises(ContractError):
            await codex.executor().submit("Corrige le test.")


async def test_the_plugin_builds_an_executor_described_by_its_configuration(tmp_path: Path) -> None:
    settings = CodexSettings(
        working_directory=CWD, description="corriger le code", sandbox=Sandbox.READ_ONLY, model="gpt-6.1"
    )
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    executor = build(settings, "codex-vps", services)
    assert (executor.name, executor.description, executor.brand) == ("codex-vps", "corriger le code", "codex")
    assert executor.details() == {"sandbox": "read-only", "model": "gpt-6.1"}
    assert executor.health() is Health.STARTED


@pytest.mark.live
@pytest.mark.skipif(shutil.which("codex") is None, reason="needs the codex command, signed in")
async def test_live_codex_writes_a_file_and_hands_it_back(tmp_path: Path) -> None:
    """Runs a real turn (cost) in a temporary directory, sandboxed to it."""
    async with build(
        CodexSettings(working_directory=str(tmp_path.resolve()), description="write files"),
        "codex",
        Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("en")),
    ) as executor:
        ref = await executor.submit("Write a file hello.txt containing the word bonjour, then report.")
        first = await executor.follow(ref, Progress())
    assert first.status is TaskStatus.COMPLETED, first
    assert [(f.name, f.data.strip()) for f in first.files] == [("hello.txt", b"bonjour")], json.dumps(first.result)
