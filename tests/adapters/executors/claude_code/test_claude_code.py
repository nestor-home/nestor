"""Claude Code executor: the executor contract against a fake `claude` command, then what only a headless process can
break (its arguments, its session from turn to turn, an instruction while it works, a crash, a stop it ignores, files
out of its folder)."""

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
from nestor.modules.cognition.delegation import Assignment, NestorAccess, Progress, TurnStatus
from nestor.modules.journal import BlobRef, FileRef
from nestor.runtime import Services
from nestor.testing.cognition import ExecutorContract
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore

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

    def asking_executor(self) -> ClaudeCodeExecutor:
        return claude(self.tmp_path, "ask")


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
        await executor.run(Assignment("--help me: corrige le test"), Progress(steps.append))
    seen = json.loads(record.read_text())
    arguments: list[str] = seen["arguments"]

    def given(flag: str) -> str:
        return arguments[arguments.index(flag) + 1]

    assert seen["instruction"].startswith("--help me: corrige le test") and seen["api_key"] == "sk-ant-test"
    assert Path(seen["cwd"]) == tmp_path.resolve() / "task", "in the task's own folder, under the working directory"
    assert "sk-ant-test" not in " ".join(arguments)
    assert {"-p", "--verbose"} <= set(arguments) and "--resume" not in arguments
    assert (given("--input-format"), given("--output-format")) == ("stream-json", "stream-json")
    assert steps[0] == f"session {given('--session-id')}"
    assert (given("--model"), given("--permission-mode"), given("--max-budget-usd")) == ("sonnet", "acceptEdits", "0.5")
    assert (given("--allowedTools"), given("--disallowedTools")) == ("Read,Bash(git *)", "WebFetch")
    assert given("--append-system-prompt").startswith("Sois bref.")
    assert "`files`" in given("--append-system-prompt") and "`question`" in given("--append-system-prompt")
    assert json.loads(given("--json-schema"))["required"] == ["report", "files", "question"]


async def test_the_report_comes_back_with_its_files_and_the_tool_calls_are_progress(tmp_path: Path) -> None:
    steps: list[str] = []
    async with claude(tmp_path) as executor:
        outcome = await executor.run(Assignment("Écris le rapport.", folder="task-1"), Progress(steps.append))
    assert (outcome.result, outcome.session) == ("Rapport écrit.", steps[0].removeprefix("session "))
    assert [(f.name, f.kind, f.media_type, f.data) for f in outcome.files] == [
        ("rapport.md", AttachmentKind.FILE, "text/markdown", b"# Rapport")
    ]
    assert steps[1:] == [f"Write: {tmp_path.resolve()}/task-1/rapport.md", "Bash", "TodoWrite"]
    assert not any("sk-secret" in step or "curl" in step for step in steps), "never a command line in the journal"


async def test_a_turn_given_its_session_resumes_it_in_the_task_s_folder(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    seen = []
    async with claude(tmp_path, record=("--record", str(record))) as executor:
        first = await executor.run(Assignment("Écris le rapport.", folder="task-1"), Progress())
        seen.append(json.loads(record.read_text()))
        then = await executor.run(Assignment("Raccourcis-le.", first.session, folder="task-1"), Progress())
        seen.append(json.loads(record.read_text()))
    arguments: list[str] = seen[1]["arguments"]
    assert first.session and then.session == first.session
    assert arguments[arguments.index("--resume") + 1] == first.session and "--session-id" not in arguments
    assert seen[1]["cwd"] == seen[0]["cwd"] and "rapport.md" in seen[1]["found"], "the same folder, as it was left"


async def test_a_report_with_a_question_ends_the_turn_on_it(tmp_path: Path) -> None:
    async with claude(tmp_path, "ask") as executor:
        outcome = await executor.run(Assignment("Choisis un devis."), Progress())
    assert (outcome.status, outcome.question, outcome.result) == (
        TurnStatus.ASKED,
        "Lequel garder ?",
        "J'ai trouvé deux devis.",
    )
    assert outcome.session


async def test_an_instruction_while_it_works_reaches_its_process_and_not_once_it_ended(tmp_path: Path) -> None:
    handles: list[str] = []
    async with claude(tmp_path, "steered") as executor:
        job = asyncio.create_task(executor.run(Assignment("Corrige le devis."), Progress(on_attach=handles.append)))
        while not handles:
            await asyncio.sleep(0.01)
        assert await executor.steer(handles[0], "Garde le même prix.")
        outcome = await asyncio.wait_for(job, 20)
        assert not await executor.steer(handles[0], "Et la TVA ?"), "the turn has ended"
    assert (outcome.status, outcome.result, outcome.session) == (
        TurnStatus.COMPLETED,
        "Fait, avec : Garde le même prix.",
        handles[0],
    )


@pytest.mark.parametrize(("behave", "report"), [("text", "Fini."), ("odd", '{"summary": "Fini."}'), ("huge", "Fini.")])
async def test_a_result_without_a_structured_report_is_the_report(tmp_path: Path, behave: str, report: str) -> None:
    async with claude(tmp_path, behave) as executor:
        outcome = await asyncio.wait_for(executor.run(Assignment("Lance les tests."), Progress()), 20)
    assert (outcome.status, outcome.result, outcome.files) == (TurnStatus.COMPLETED, report, ())


@pytest.mark.parametrize(
    ("behave", "error"),
    [
        ("fail", "error_max_budget_usd"),
        ("crash", "Claude Code ended without a result (exit 1): Invalid API key · Please run /login"),
    ],
)
async def test_a_failed_or_crashed_run_is_a_failure_with_its_reason(tmp_path: Path, behave: str, error: str) -> None:
    async with claude(tmp_path, behave) as executor:
        outcome = await executor.run(Assignment("Corrige le test."), Progress())
    assert (outcome.status, outcome.error) == (TurnStatus.FAILED, error)


async def test_only_files_within_the_task_s_own_folder_come_back(tmp_path: Path) -> None:
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "secret.txt").write_text("secret")  # in the working directory, another task's say
    async with claude(folder, "files", max_file_bytes=1_000) as executor:
        outcome = await executor.run(Assignment("Fais les fichiers."), Progress())
    assert [(f.name, f.data) for f in outcome.files] == [("ok.txt", b"ok")]
    assert outcome.result is not None and outcome.result.startswith("Fichiers faits.\nFiles left out: ")
    for name, why in [
        ("link.txt", "outside the working directory"),
        ("big.bin", "larger than 1000 bytes"),
        ("sub", "not a file"),
        ("missing.txt", "missing"),
    ]:
        assert f"{name} ({why})" in outcome.result, name


async def test_the_files_sent_with_a_task_wait_in_its_own_folder_and_the_brief_names_them(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    store = MemoryBlobStore()
    gone = FileRef(BlobRef("0" * 64, 3, "image/png"), "photo.png")  # no longer stored: neither placed nor named
    sent = (FileRef(await store.put(b"%PDF devis", "application/pdf"), "devis.pdf"), gone)
    folders = []
    async with claude(tmp_path / "work", record=("--record", str(record))) as executor:
        (tmp_path / "work").mkdir()
        for task in ("task-1", "task-2"):
            await executor.run(Assignment("Corrige le devis.", folder=task, files=sent, reader=store.get), Progress())
            seen = json.loads(record.read_text())
            folders.append(seen["cwd"])
            assert seen["found"] == {"devis.pdf": "%PDF devis"}
            assert f"Files sent with this instruction, in {seen['cwd']}: devis.pdf." in seen["instruction"]
    assert folders[0] != folders[1], "each task its own folder"


async def test_a_stop_ends_even_a_process_that_ignores_it(tmp_path: Path) -> None:
    async with claude(tmp_path, "stubborn", stop_timeout_s=0.3) as executor:
        job = asyncio.create_task(executor.run(Assignment("Corrige le test."), Progress()))
        await asyncio.sleep(1.0)
        job.cancel()
        outcome = await asyncio.wait_for(job, 10)
    assert outcome.status is TurnStatus.STOPPED and outcome.session, "stopped, its session kept to go on in"


async def test_a_claude_that_is_not_installed_fails_the_task_and_is_unavailable(tmp_path: Path) -> None:
    executor = ClaudeCodeExecutor(["claude-that-is-not-installed"], working_directory=tmp_path, description="code")
    async with executor:
        outcome = await executor.run(Assignment("Corrige le test."), Progress())
    assert outcome.status is TurnStatus.FAILED and "could not start" in (outcome.error or "")
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
        outcome = await executor.run(
            Assignment("Write a file hello.txt containing the word bonjour, then report."), Progress()
        )
    assert outcome.status is TurnStatus.COMPLETED, outcome
    assert [(f.name, f.data.strip()) for f in outcome.files] == [("hello.txt", b"bonjour")]


async def test_nestor_s_mcp_server_is_given_in_a_private_file_never_on_the_command_line(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    executor = claude(tmp_path, record=("--record", str(record)), allowed_tools=["Read"])
    access = NestorAccess(url="https://nestor.example/mcp", key="nstx_secret-key")
    async with executor:
        await executor.run(Assignment("Corrige le test.", task="nstt_task", access=access), Progress())
    seen = json.loads(record.read_text())
    arguments: list[str] = seen["arguments"]
    server = {"type": "http", "url": access.url, "headers": {"Authorization": "Bearer nstx_secret-key"}}
    assert seen["mcp"] == {"mcpServers": {"nestor": server}} and seen["mcp_mode"] == 0o600
    assert not any("nstx_secret-key" in a for a in arguments), "the key stays off the command line"
    assert not Path(arguments[arguments.index("--mcp-config") + 1]).exists(), "removed once the session ends"
    assert arguments[arguments.index("--allowedTools") + 1] == "Read,mcp__nestor"
    assert seen["instruction"].startswith("Corrige le test.") and 'task="nstt_task"' in seen["instruction"]


async def test_without_nestor_s_server_the_session_gets_neither_it_nor_its_tools(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    async with claude(tmp_path, record=("--record", str(record))) as executor:
        await executor.run(Assignment("Corrige le test."), Progress())
    seen = json.loads(record.read_text())
    assert seen["mcp"] is None and "--mcp-config" not in seen["arguments"]
    assert "nestor" not in seen["instruction"] and not any("mcp__nestor" in a for a in seen["arguments"])
