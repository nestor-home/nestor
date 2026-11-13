"""What the executors share: the instructions a task comes with, the report a coding agent ends with, and the
files it hands back.

A coding agent (Codex, Claude Code) ends its task with a structured report (`REPORT_SCHEMA`): the text for the
assistant, and the absolute paths of the files it made for the requester. Those files are read back from the
working directory only, within a size and count limit; what is left out is said at the end of the report.
"""

import json
import mimetypes
import posixpath
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition import Outcome

INSTRUCTIONS = (
    "You carry out a task handed over by a home voice assistant. Use your tools and check the result, "
    "then write a short, factual report in the language of the task: what was done or found, and what "
    "could not be. No Markdown: the assistant will say it aloud. Never claim an action you did not perform."
)
FILES_INSTRUCTIONS = (
    " If you made files for the requester (a document, a picture), put them in the working directory and list "
    "their absolute paths in `files`; leave it empty otherwise."
)
REPORT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"report": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}},
    "required": ["report", "files"],
    "additionalProperties": False,
}
MAX_STEP_LENGTH = 160
MAX_FILES = 10
MAX_FILE_BYTES = 20_000_000


def step(text: str) -> str:
    """A progress step as the journal keeps it: one short line."""
    return " ".join(text.split())[:MAX_STEP_LENGTH]


def described(error: BaseException) -> str:
    """An error as a task's failure says it: its kind, and its message when it has one."""
    said = str(error).strip()
    return f"{type(error).__name__}: {said}" if said else type(error).__name__


class Unreadable(Exception):
    """A listed file that cannot be handed back: missing, not a regular file, too large."""


@dataclass(frozen=True, slots=True)
class Report:
    """What the agent ended with: `text` for the assistant, `files` it made, as it listed them."""

    text: str
    files: tuple[str, ...] = ()

    @classmethod
    def of(cls, reply: object) -> "Report":
        """From the structured report, as an object or its JSON text; any other reply is the report itself."""
        value = reply
        if isinstance(reply, str):
            try:
                value = json.loads(reply)
            except ValueError:
                return cls(reply)
        if isinstance(value, dict) and isinstance(value.get("report"), str):
            files = value.get("files")
            listed = tuple(f for f in files if isinstance(f, str) and f) if isinstance(files, list) else ()
            return cls(value["report"], listed)
        return cls(reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False))

    async def outcome(self, root: str, read: Callable[[str], Awaitable[bytes]]) -> Outcome:
        """The completed outcome, with the files read back by `read` (which raises `Unreadable`, for a file too
        large too); only those under `root`, at most `MAX_FILES`. The report says which were left out and why: the
        assistant tells the person."""
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
        return Outcome.completed(text, tuple(files))


def attachment(path: str, data: bytes) -> Attachment:
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Attachment(
        kind=AttachmentKind.of(media_type), data=data, media_type=media_type, name=posixpath.basename(path)
    )
