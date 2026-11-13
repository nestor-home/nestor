"""Claude Code executor: the executor contract against a fake `claude` command, then what only a headless process can
break (its arguments, a crash, a stop it ignores, files out of its folder)."""

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from nestor.adapters.executors.claude_code import ClaudeCodeExecutor, ClaudeCodeSettings, PermissionMode, build
from nestor.core import Health
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import Progress, TaskStatus
from nestor.runtime import Services
from nestor.testing.cognition import ExecutorContract
from nestor.testing.i18n import EchoLocalizer

FAKE = Path(__file__).with_name("fake_claude.py")


def claude(folder: Path, behave: str = "complete", **options: Any) -> ClaudeCodeExecutor:
    options.setdefault("description", "write and fix code")
    command = [sys.executable, str(FAKE), "--behave", behave, *options.pop("record", ())]
    return ClaudeCodeExecutor(command, working_directory=folder, **options)


class TestClaudeCodeExecutor(ExecutorContract):
    @pytest.fixture(autouse=True)
    def folder(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def executor(self) -> ClaudeCodeExecutor:
        return claude(self.tmp_path)

    def slow_executor(self) -> ClaudeCodeExecutor:
        return claude(self.tmp_path, "slow")

    def failing_executor(self) -> ClaudeCodeExecutor:
        return claude(self.tmp_path, "fail")


async def test_the_session_runs_where_and_how_the_configuration_says(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    steps: list[str] = []
    executor = claude(
        tmp_path,
        record=("--record", str(record)),
        model="sonnet",
        permission_mode=PermissionMode.ACCEPT_EDITS,
        allowed_tools=["Read", "Bash(git *)"],
        disallowed_tools=["WebFetch"],
        max_budget_usd=0.5,
        api_key="sk-ant-test",
        instructions="Sois bref.",
    )
    async with executor:
        await executor.run("--help me: corrige le test", Progress(steps.append))
    seen = json.loads(record.read_text())
    arguments: list[str] = seen["arguments"]

    def given(flag: str) -> str:
        return arguments[arguments.index(flag) + 1]

    assert (seen["objective"], seen["cwd"], seen["api_key"]) == (
        "--help me: corrige le test",
        str(tmp_path.resolve()),
        "sk-ant-test",
    )
    assert "sk-ant-test" not in " ".join(arguments)
    assert {"-p", "--verbose"} <= set(arguments) and given("--output-format") == "stream-json"
    assert steps[0] == f"session {given('--session-id')}"
    assert (given("--model"), given("--permission-mode"), given("--max-budget-usd")) == ("sonnet", "acceptEdits", "0.5")
    assert (given("--allowedTools"), given("--disallowedTools")) == ("Read,Bash(git *)", "WebFetch")
    assert given("--append-system-prompt").startswith("Sois bref.") and "`files`" in given("--append-system-prompt")
    assert json.loads(given("--json-schema"))["required"] == ["report", "files"]


async def test_the_report_comes_back_with_its_files_and_the_tool_calls_are_progress(tmp_path: Path) -> None:
    steps: list[str] = []
    async with claude(tmp_path) as executor:
        outcome = await executor.run("Écris le rapport.", Progress(steps.append))
    assert outcome.result == "Rapport écrit."
    assert [(f.name, f.kind, f.media_type, f.data) for f in outcome.files] == [
        ("rapport.md", AttachmentKind.FILE, "text/markdown", b"# Rapport")
    ]
    assert steps[1:] == [f"Write: {tmp_path.resolve() / 'rapport.md'}", "Bash: ls -la", "TodoWrite"]


@pytest.mark.parametrize(("behave", "report"), [("text", "Fini."), ("odd", '{"summary": "Fini."}'), ("huge", "Fini.")])
async def test_a_result_without_a_structured_report_is_the_report(tmp_path: Path, behave: str, report: str) -> None:
    async with claude(tmp_path, behave) as executor:
        outcome = await asyncio.wait_for(executor.run("Lance les tests.", Progress()), 20)
    assert (outcome.status, outcome.result, outcome.files) == (TaskStatus.COMPLETED, report, ())


@pytest.mark.parametrize(
    ("behave", "error"),
    [
        ("fail", "error_max_budget_usd"),
        ("crash", "Claude Code ended without a result (exit 1): Invalid API key · Please run /login"),
    ],
)
async def test_a_failed_or_crashed_run_is_a_failure_with_its_reason(tmp_path: Path, behave: str, error: str) -> None:
    async with claude(tmp_path, behave) as executor:
        outcome = await executor.run("Corrige le test.", Progress())
    assert (outcome.status, outcome.error) == (TaskStatus.FAILED, error)


async def test_only_files_within_the_working_directory_come_back(tmp_path: Path) -> None:
    folder = tmp_path / "work"
    folder.mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    async with claude(folder, "files", max_file_bytes=1_000) as executor:
        outcome = await executor.run("Fais les fichiers.", Progress())
    assert [(f.name, f.data) for f in outcome.files] == [("ok.txt", b"ok")]
    assert outcome.result is not None and outcome.result.startswith("Fichiers faits.\nFiles left out: ")
    for name, why in [
        ("link.txt", "outside the working directory"),
        ("big.bin", "larger than 1000 bytes"),
        ("sub", "not a file"),
        ("missing.txt", "missing"),
    ]:
        assert f"{name} ({why})" in outcome.result, name


async def test_a_stop_ends_even_a_process_that_ignores_it(tmp_path: Path) -> None:
    async with claude(tmp_path, "stubborn", stop_timeout_s=0.3) as executor:
        job = asyncio.create_task(executor.run("Corrige le test.", Progress()))
        await asyncio.sleep(1.0)
        job.cancel()
        outcome = await asyncio.wait_for(job, 10)
    assert outcome.status is TaskStatus.CANCELLED


async def test_a_claude_that_is_not_installed_fails_the_task_and_is_unavailable(tmp_path: Path) -> None:
    executor = ClaudeCodeExecutor(["claude-that-is-not-installed"], working_directory=tmp_path, description="code")
    async with executor:
        outcome = await executor.run("Corrige le test.", Progress())
    assert outcome.status is TaskStatus.FAILED and "could not start" in (outcome.error or "")
    assert (executor.health(), executor.health_detail()) == (
        Health.UNAVAILABLE,
        Message.of("health-executor-unreachable", executor="claude-code"),
    )


async def test_the_plugin_builds_an_executor_described_by_its_configuration(tmp_path: Path) -> None:
    settings = ClaudeCodeSettings(
        command=[sys.executable], working_directory=tmp_path, description="corriger le code", api_key="sk-ant-x"
    )
    executor = build(settings, "claude", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR")))
    assert (executor.name, executor.description, executor.brand) == ("claude", "corriger le code", "claude-code")
    assert executor.details() == {"permission_mode": "dontAsk"} and executor.health() is Health.STARTED


@pytest.mark.live
@pytest.mark.skipif(shutil.which("claude") is None, reason="needs the claude command, signed in")
async def test_live_claude_code_writes_a_file_and_hands_it_back(tmp_path: Path) -> None:
    """Runs a real session (cost) in a temporary directory."""
    executor = ClaudeCodeExecutor(
        working_directory=tmp_path, description="write files", model="haiku", max_budget_usd=0.2
    )
    async with executor:
        outcome = await executor.run("Write a file hello.txt containing the word bonjour, then report.", Progress())
    assert outcome.status is TaskStatus.COMPLETED, outcome
    assert [(f.name, f.data.strip()) for f in outcome.files] == [("hello.txt", b"bonjour")]
