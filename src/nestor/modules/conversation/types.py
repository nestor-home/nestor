"""Values of the dialogue, shared by every channel."""

from dataclasses import dataclass
from enum import StrEnum

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


@dataclass(frozen=True, slots=True)
class Notification:
    """What Nestor brings into a conversation by itself, as a tool's result comes back to a model: a task ended, a
    watch matched, a message to pass on. It opens a turn as a person's message does, the answer follows, and both
    stay in the conversation's history. `about` names what it comes from (`task 3f2a completed`)."""

    text: str
    about: str

    def __post_init__(self) -> None:
        if len(self.text) > NOTIFICATION_CHARS:
            half = NOTIFICATION_CHARS // 2
            object.__setattr__(self, "text", f"{self.text[:half]}\n[… cut …]\n{self.text[-half:]}")
