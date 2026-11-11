"""Values of the dialogue, shared by every channel."""

from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.channels import AttachmentKind
from nestor.modules.journal import BlobRef

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
    WATCH = "watch"  # a watch matched
    SCHEDULE = "schedule"  # a wake-up is due
    MESSAGE = "message"  # a message to pass on
    CONFIRMATION = "confirmation"  # a sensitive action to confirm, or its result


@dataclass(frozen=True, slots=True)
class About:
    """What a notification comes from: `task 3f2a completed`. `status` says how it stands, when that matters to
    whoever reads it: a task `completed`, a call `failed`, a message `undelivered`, a confirmation `done`."""

    source: Source
    id: str
    status: str = ""

    def __str__(self) -> str:
        return " ".join(part for part in (self.source.value, self.id, self.status) if part)

    @property
    def key(self) -> str:
        """What every notification about the same thing shares, whatever its status: `task:3f2a`."""
        return f"{self.source.value}:{self.id}"


SILENT = "[SILENT]"  # the whole answer to a notification that may stay silent, when there is nothing to tell


@dataclass(frozen=True, slots=True)
class Notification:
    """What Nestor brings into a conversation by itself, as a tool's result comes back to a model: a task ended, a
    watch matched, a message to pass on. It opens a turn as a person's message does, the answer follows, and both
    stay in the conversation's history. `text` gives the facts and what to do; how to answer is the persona's.
    `quiet`: the answer may be nothing (a check that found nothing); otherwise saying nothing is a failure."""

    text: str
    about: About
    quiet: bool = False

    def __post_init__(self) -> None:
        if len(self.text) > NOTIFICATION_CHARS:
            half = NOTIFICATION_CHARS // 2
            object.__setattr__(self, "text", f"{self.text[:half]}\n[… cut …]\n{self.text[-half:]}")


@dataclass(frozen=True, slots=True)
class Attached:
    """A file that came with a person's message, as the journal keeps it: stored by content (`blob`), and what was
    said in it when it is a recording that could be transcribed."""

    kind: AttachmentKind
    blob: BlobRef
    name: str | None = None
    transcript: str | None = None
