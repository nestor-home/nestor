"""Values of delegated tasks: status, outcome, progress reporting and how to deliver the result."""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from nestor.core import Capability
from nestor.modules.channels import Attachment
from nestor.modules.journal import FileRef

RESUME = Capability("delegation.resume")


class TaskStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NestorTools(StrEnum):
    """How an executor reaches Nestor's MCP server while it works: its brief, its memory of the requester, questions
    to them, its progress and its files."""

    NONE = "none"  # it does not
    PASSED = "passed"  # Nestor passes the server's address and the executor's key with each task (Codex, Claude Code)
    CONFIGURED = "configured"  # its own configuration holds them, set once (Hermes's profile)


@dataclass(frozen=True, slots=True, kw_only=True)
class NestorAccess:
    """Where Nestor's MCP server is, and the executor's key for it (`Authorization: Bearer`)."""

    url: str
    key: str = field(repr=False)


BRIEF = """Nestor, the household assistant that handed you this task, gives you tools for it through its MCP server \
`nestor`. Call each with task="{task}": task_brief first (who asked, the conversation it came from); recall and \
remember for what you need to know of them; report_progress at each step; ask_requester when you need them rather \
than guessing or giving up, then check_answer later.{links} Never write the task value anywhere else."""
PLACED = "Files sent with the task, in {folder}: {names}."
BY_LINK = """ read_file gives a link to download a file they sent (task_brief lists them), attach_file a link to \
upload each file you make for them; each link works a few minutes, with curl or any HTTP client."""


@dataclass(frozen=True, slots=True)
class Assignment:
    """What an executor is given: the objective, the files sent with it, and when it reaches Nestor's tools, the
    task's capability (`task`, `nstt_…`) its tools take, valid while the task runs, and `access` when Nestor passes the
    server itself. `files` are references: an executor that places them in a folder of its own reads them (`placed`),
    one reached by link never does."""

    objective: str
    task: str | None = field(default=None, repr=False)
    access: NestorAccess | None = None
    files: tuple[FileRef, ...] = ()  # names plain and none twice among a task's files
    reader: Callable[[str], Awaitable[bytes]] | None = field(default=None, repr=False, compare=False)

    async def placed(self) -> AsyncIterator[tuple[str, bytes]]:
        """The files sent with it, by name and content, read one at a time; one no longer stored is left out."""
        if self.reader is None:
            return
        for file in self.files:
            try:
                yield file.name, await self.reader(file.blob.digest)
            except KeyError:
                continue

    def brief(self, folder: str | None = None, placed: Sequence[str] = ()) -> str:
        """The objective, the files the executor `placed` in its `folder`, and how to reach Nestor's tools when it
        can: the files by link, without a folder."""
        parts = [self.objective]
        if folder is not None and placed:
            parts.append(PLACED.format(folder=folder, names=", ".join(placed)))
        if self.task is not None:
            parts.append(BRIEF.format(task=self.task, links=BY_LINK if folder is None else ""))
        return "\n\n".join(parts)


class Notify(StrEnum):
    """Where the requester wants the result."""

    AUTO = "auto"  # in the conversation if they are still in it, else where they can be reached
    MESSAGE = "message"  # in writing, wherever they are ("écris-moi quand c'est fini")


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a task ended: its report, or why it failed. `files` are what the executor made for the requester (a
    document, a picture): they go with the answer that brings the result, where the channel can send them."""

    status: TaskStatus
    result: str | None = None
    error: str | None = None
    files: tuple[Attachment, ...] = ()

    @classmethod
    def completed(cls, result: str, files: tuple[Attachment, ...] = ()) -> "Outcome":
        return cls(TaskStatus.COMPLETED, result=result, files=files)

    @classmethod
    def failed(cls, error: str) -> "Outcome":
        return cls(TaskStatus.FAILED, error=error)

    @classmethod
    def cancelled(cls) -> "Outcome":
        return cls(TaskStatus.CANCELLED)


def _ignore(_: str) -> None:
    return None


class Progress:
    """How an executor reports while it works: steps (`progress("searching…")`) and, for remote
    work, the handle that lets Nestor follow it again after a restart (`progress.attach(ref)`)."""

    def __init__(self, on_step: Callable[[str], None] = _ignore, on_attach: Callable[[str], None] = _ignore) -> None:
        self._on_step, self._on_attach = on_step, on_attach

    def __call__(self, step: str) -> None:
        self._on_step(step)

    def attach(self, ref: str) -> None:
        self._on_attach(ref)
