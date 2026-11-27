"""Values of the dialogue, shared by every channel."""

from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.journal import BlobRef, FileRef

NOTIFICATION_CHARS = (
    8000  # of what a notification brings into a conversation: a task's long result keeps its beginning and end
)


class FallbackReason(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_SLOW = "model_slow"
    RECOGNITION_UNAVAILABLE = "recognition_unavailable"
    SYNTHESIS_UNAVAILABLE = "synthesis_unavailable"


class ReplyPhase(StrEnum):
    """Where an answer being produced stands."""

    THINKING = "thinking"  # nothing said yet, or tools running between two rounds
    SPEAKING = "speaking"  # its words are coming out to the channel


class Source(StrEnum):
    """What brings a notification."""

    TASK = "task"  # a delegated task ended
    TOOL = "tool"  # a call that went on in the background answered
    ALERT = "alert"  # an alert rang
    MESSAGE = "message"  # a message to pass on
    CONFIRMATION = "confirmation"  # a sensitive action to confirm, or its result


@dataclass(frozen=True, slots=True)
class About:
    """What a notification comes from: `task 3f2a completed`. `status` says how it stands, when that matters to
    whoever reads it: a task `completed`, a call `failed`, a message `undelivered`, a confirmation `done`. `part`
    names which part of it, when it has several: a task's turn."""

    source: Source
    id: str
    status: str = ""
    part: str = ""

    def __str__(self) -> str:
        return " ".join(part for part in (self.source.value, self.id, self.status) if part)

    @property
    def key(self) -> str:
        """What every notification about the same thing shares, whatever its status or part: `task:3f2a`."""
        return f"{self.source.value}:{self.id}"

    def same(self, other: "About") -> bool:
        """Whether `other` is about the same thing and the same part of it, whatever its status."""
        return (self.key, self.part) == (other.key, other.part)


SILENT = "[SILENT]"  # opens the answer to a notification with nothing to tell; what follows it is the reason


@dataclass(frozen=True, slots=True)
class Notification:
    """What Nestor brings into a conversation by itself, as a tool's result comes back to a model: a task ended, an
    alert rang, a message to pass on. It opens a turn as a person's message does, the answer follows, and both
    stay in the conversation's history. `text` gives the facts and what to do; how to answer is the persona's. It may
    go unanswered when there is nothing to tell (a check that found nothing), unless `must_tell`: a message someone
    asked to pass on, a confirmation to ask for, where saying nothing is a failure.

    `thread` is what it continues: an alert that rings again and the tasks started from its turns share one, so that
    what was told in it is read back before the next one is answered, and only what is new is told."""

    text: str
    about: About
    must_tell: bool = False
    files: tuple[FileRef, ...] = ()  # what a tool made, to go with the answer
    thread: str | None = None
    seen: tuple[FileRef, ...] = ()  # pictures a tool took, for the model to look at

    def __post_init__(self) -> None:
        if len(self.text) > NOTIFICATION_CHARS:
            half = NOTIFICATION_CHARS // 2
            object.__setattr__(self, "text", f"{self.text[:half]}\n[… cut …]\n{self.text[-half:]}")


@dataclass(frozen=True, slots=True)
class Outgoing:
    """Files that go with a message: to send, and as the journal keeps them (`AnswerAttached`)."""

    sent: tuple[Attachment, ...] = ()
    kept: tuple["Attached", ...] = ()

    def __add__(self, other: "Outgoing") -> "Outgoing":
        return Outgoing(self.sent + other.sent, self.kept + other.kept)


@dataclass(frozen=True, slots=True)
class Read:
    """What was read of a document: `ref` reads its text with `read_result`; `None` when it has no text (a scan).
    `pages` when the reader counted them (a PDF)."""

    ref: str | None
    pages: int | None = None


@dataclass(frozen=True, slots=True)
class Attached:
    """A file that came with a person's message, as the journal keeps it: stored by content (`blob`), what was
    said in it when it is a recording that could be transcribed, and what was read of it when it is a document."""

    kind: AttachmentKind
    blob: BlobRef
    name: str | None = None
    transcript: str | None = None
    read: Read | None = None


class MentionKind(StrEnum):
    """What a message can name with `@`."""

    PERSON = "person"  # someone of the household
    ROOM = "room"  # a room of the home
    DEVICE = "device"  # something of the home, as its system names it
    EXECUTOR = "executor"  # an executor, to hand work to
    CONNECTION = "connection"  # a connected account (a mailbox, a calendar), to use
    TASK = "task"  # a task of whoever writes, to direct


@dataclass(frozen=True, slots=True, kw_only=True)
class Mentioned:
    """Something a message names as `@handle`, whatever the channel: names people type, never an id. `handle` is the
    one offered, unique for whoever writes; `aliases` are other names it answers to (a person's name, a room's, an
    account's). `label` is how it reads ("Mathilde", "Salon", "mathis@gmail.com"), `detail` what tells it apart (what
    an executor does), `brand` the vendor behind it, when there is one."""

    kind: MentionKind
    id: str  # the person, room, executor or connection it is
    handle: str
    label: str
    aliases: tuple[str, ...] = ()
    detail: str = ""
    brand: str | None = None
