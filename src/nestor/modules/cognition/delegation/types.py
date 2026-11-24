"""Values of delegated tasks: a task is a thread of turns with an executor; each turn ends with an outcome (a report, a
question, a failure, a stop), and the task is working, waiting for its owner, ready to go on, or archived."""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from nestor.core import Capability
from nestor.modules.channels import Attachment
from nestor.modules.journal import FileRef

RESUME = Capability("delegation.resume")  # its turns run elsewhere and outlive Nestor: followed again after a restart
CONTINUE = Capability("delegation.continue")  # a turn goes on in the session of the turns before it
STEER = Capability("delegation.steer")  # an instruction reaches the turn while it works


class TurnStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"  # it reported
    ASKED = "asked"  # it needs its owner: its question is the turn's end
    FAILED = "failed"
    STOPPED = "stopped"


class TaskState(StrEnum):
    WORKING = "working"  # a turn runs
    WAITING = "waiting"  # its last turn asked its owner a question
    READY = "ready"  # its last turn ended: it goes on when given an instruction
    ARCHIVED = "archived"  # put away; an instruction opens it again


class NestorTools(StrEnum):
    """How an executor reaches Nestor's MCP server while it works: its brief, its notes, its progress and its files."""

    NONE = "none"  # it does not
    PASSED = "passed"  # Nestor passes the server's address and the executor's key with each turn (Codex, Claude Code)
    CONFIGURED = "configured"  # its own configuration holds them, set once (Hermes's profile)


@dataclass(frozen=True, slots=True, kw_only=True)
class NestorAccess:
    """Where Nestor's MCP server is, and the executor's key for it (`Authorization: Bearer`)."""

    url: str
    key: str = field(repr=False)


BRIEF = """Nestor, the household assistant that handed you this task, gives you tools for it through its MCP server \
`nestor`. Call each with task="{task}": task_brief first (who asked, the conversation it came from, the turns before \
this one); recall for what you need to know of them; note to keep what this task will need later; report_progress at \
each step.{links} Never write the task value anywhere else."""
ASKING = """When you need the person to go on (a choice, a detail, an action only they can take), do not guess and do \
not give up: end your turn with your question in `question` and what you did so far in `report`. Their answer comes \
back as your next instruction, in this same session."""
PLACED = "Files sent with this instruction, in {folder}: {names}."
BY_LINK = """ read_file gives a link to download a file they sent (task_brief lists them), attach_file a link to \
upload each file you make for them; each link works a few minutes, with curl or any HTTP client."""
EARLIER = """The turns before this one, as Nestor kept them (you do not remember them):
{turns}"""


@dataclass(frozen=True, slots=True)
class Assignment:
    """One turn of a task, as its executor is given it: the instruction, the session of the turns before it (`None`
    for the first; what the executor's last outcome named), what they were (`earlier`, for an executor that cannot
    continue a session), the task's own `folder` for an executor that works in one, the files sent with the
    instruction, and when it reaches Nestor's tools, the turn's capability (`task`, `nstt_…`), valid while it runs,
    and `access` when Nestor passes the server itself. `files` are references: an executor that places them in its
    folder reads them (`placed`), one reached by link never does."""

    instruction: str
    session: str | None = None
    earlier: str = ""
    folder: str = "task"
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
        """The instruction, the turns before it when the executor does not keep them, the files it `placed` in its
        `folder`, how to ask the person, and how to reach Nestor's tools when it can: the files by link, without a
        folder."""
        parts = [self.instruction]
        if self.earlier:
            parts.append(EARLIER.format(turns=self.earlier))
        if folder is not None and placed:
            parts.append(PLACED.format(folder=folder, names=", ".join(placed)))
        parts.append(ASKING)
        if self.task is not None:
            parts.append(BRIEF.format(task=self.task, links=BY_LINK if folder is None else ""))
        return "\n\n".join(parts)


class Notify(StrEnum):
    """Where the person wants what a turn comes back with."""

    AUTO = "auto"  # in the conversation if they are still in it, else where they can be reached
    MESSAGE = "message"  # in writing, wherever they are ("écris-moi quand c'est fini")


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a turn ended: its report, the question it asks its owner, or why it failed. `files` are what the executor
    made for them (a document, a picture): they go with the answer that brings the outcome. `session` is what the
    next turn continues, when the executor keeps one (a Codex thread, a Claude Code session)."""

    status: TurnStatus
    result: str | None = None
    question: str | None = None
    error: str | None = None
    files: tuple[Attachment, ...] = ()
    session: str | None = None

    @classmethod
    def completed(cls, result: str, files: tuple[Attachment, ...] = (), *, session: str | None = None) -> "Outcome":
        return cls(TurnStatus.COMPLETED, result=result, files=files, session=session)

    @classmethod
    def asked(
        cls, question: str, result: str = "", files: tuple[Attachment, ...] = (), *, session: str | None = None
    ) -> "Outcome":
        return cls(TurnStatus.ASKED, result=result or None, question=question, files=files, session=session)

    @classmethod
    def failed(cls, error: str, *, session: str | None = None) -> "Outcome":
        return cls(TurnStatus.FAILED, error=error, session=session)

    @classmethod
    def stopped(cls, *, session: str | None = None) -> "Outcome":
        return cls(TurnStatus.STOPPED, session=session)


def _ignore(_: str) -> None:
    return None


class Progress:
    """How an executor reports while a turn works: steps (`progress("searching…")`), and the handle of the turn
    (`progress.attach(ref)`): what follows remote work again after a restart, and what an instruction is steered to."""

    def __init__(self, on_step: Callable[[str], None] = _ignore, on_attach: Callable[[str], None] = _ignore) -> None:
        self._on_step, self._on_attach = on_step, on_attach

    def __call__(self, step: str) -> None:
        self._on_step(step)

    def attach(self, ref: str) -> None:
        self._on_attach(ref)
