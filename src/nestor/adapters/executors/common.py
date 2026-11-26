"""What the executors share: the instructions a task comes with, what every executor's settings hold, the folder a
coding agent works on a task in, the report each turn ends with, and the files it hands back.

A coding agent works on each task in a folder of its own under its working directory (`Assignment.folder`, the same
for every turn of the task), where the files sent with each instruction are placed before the turn starts: it reads
them with its own tools, and the brief names them.

A coding agent (Codex, Claude Code) ends each turn with a structured report (`REPORT_SCHEMA`): the text for the
assistant, the absolute paths of the files it made for the person, and the question it asks them when it cannot go
on without them. Those files are read back from the working directory only, within a size and count limit; what is
left out is said at the end of the report.
"""

import json
import mimetypes
import posixpath
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import Field, PositiveInt

from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition import Executor, Outcome
from nestor.modules.cognition.model import json_object
from nestor.runtime.plugins import AdapterSettings

INSTRUCTIONS = (
    "You carry out a task handed over by a home voice assistant. Use your tools and check the result, "
    "then write a short, factual report in the language of the task: what was done or found, and what "
    "could not be. No Markdown: the assistant will say it aloud. Never claim an action you did not perform."
)
QUESTION_INSTRUCTIONS = (
    " When you cannot go on without the person (a choice, a detail, an action only they can take), do not guess and "
    "do not give up: end your turn with your question in `question` and what you did so far in `report`; leave "
    "`question` empty otherwise. Their answer comes back as your next instruction."
)
FILES_INSTRUCTIONS = (
    " If you made files for the requester (a document, a picture), put them in the working directory and list "
    "their absolute paths in `files`; leave it empty otherwise."
)
CODING_REPORT = FILES_INSTRUCTIONS + QUESTION_INSTRUCTIONS  # what a coding agent's report holds (`REPORT_SCHEMA`)
REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "report": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "question": {
            "type": "string",
            "description": "your question to the person when you cannot go on without them; an empty string otherwise",
        },
    },
    "required": ["report", "files", "question"],
    "additionalProperties": False,
}
MAX_FILES = 10
MAX_FILE_BYTES = 20_000_000


class ExecutorSettings(AdapterSettings):
    """What every executor's settings hold beside its own: whether it acts with real power (`sensitive`: started or
    directed from a shared device, the person confirms in writing), and how long a task it finished is kept at hand
    (`archive_after_days`; `null`: never archived)."""

    sensitive: bool = False
    archive_after_days: PositiveInt | None = Field(default=30)

    def apply[E: Executor](self, executor: E, name: str) -> E:
        """`executor`, named and set as these settings say."""
        executor.name = name  # two setups of one kind are two executors
        executor.sensitive, executor.archive_after_days = self.sensitive, self.archive_after_days
        return executor


def described(error: BaseException) -> str:
    """An error as a task's failure says it: its kind, and its message when it has one."""
    said = str(error).strip()
    return f"{type(error).__name__}: {said}" if said else type(error).__name__


class Unreadable(Exception):
    """A listed file that cannot be handed back: missing, not a regular file, too large."""


@dataclass(frozen=True, slots=True)
class Report:
    """What the agent ended its turn with: `text` for the assistant, `files` it made, as it listed them, and the
    `question` it asks the person when it cannot go on without them."""

    text: str
    files: tuple[str, ...] = ()
    question: str = ""

    @classmethod
    def of(cls, reply: object) -> "Report":
        """From the structured report, as an object or its JSON text, even fenced or after a sentence; any other
        reply is the report itself."""
        value = json_object(reply) if isinstance(reply, str) else reply
        if isinstance(value, dict) and isinstance(value.get("report"), str):
            files = value.get("files")
            listed = tuple(f for f in files if isinstance(f, str) and f) if isinstance(files, list) else ()
            question = value.get("question")
            return cls(value["report"], listed, question.strip() if isinstance(question, str) else "")
        return cls(reply.strip() if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False))

    async def outcome(self, root: str, read: Callable[[str], Awaitable[bytes]]) -> Outcome:
        """The turn's outcome: asked when it ends on a question, completed otherwise; with the files
        read back by `read` (which raises `Unreadable`, for a file too large too), only those under `root`, at most
        `MAX_FILES`. The report says which were left out and why: the assistant tells the person."""
        root = posixpath.normpath(root)
        files: list[Attachment] = []
        left: list[str] = []
        for listed in self.files:
            path = posixpath.normpath(posixpath.join(root, listed))
            if not path.startswith(posixpath.join(root, "")):
                left.append(f"{listed} (outside the working directory)")
            elif len(files) == MAX_FILES:
                left.append(f"{listed} (more than {MAX_FILES} files)")
            else:
                try:
                    data = await read(path)
                except Unreadable as error:
                    left.append(f"{listed} ({error})")
                    continue
                files.append(attachment(path, data))
        text = f"{self.text}\nFiles left out: {'; '.join(left)}" if left else self.text
        if self.question:
            return Outcome.asked(self.question, text, tuple(files))
        return Outcome.completed(text, tuple(files))


def attachment(path: str, data: bytes) -> Attachment:
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Attachment(
        kind=AttachmentKind.of(media_type), data=data, media_type=media_type, name=posixpath.basename(path)
    )
