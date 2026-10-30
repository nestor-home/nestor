"""Values of the agent's activity."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Activity(StrEnum):
    """What the agent is doing, the first that holds in this order."""

    LISTENING = "listening"  # a satellite hears someone speak
    SPEAKING = "speaking"  # an answer's words are coming out
    THINKING = "thinking"  # an answer is being prepared (model, tools), or an unprompted message composed
    WORKING = "working"  # delegated tasks are running, nothing else
    SLEEPING = "sleeping"  # within the quiet hours, nothing else
    IDLE = "idle"


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentActivity:
    state: Activity
    since: datetime  # when it entered this state, as this instance saw it
    replies: int  # answers being produced
    tasks: int  # delegated tasks running
    listening_rooms: tuple[str, ...]  # where a satellite hears someone speak, sorted
    quiet: bool  # within the quiet hours

    def same_as(self, other: "AgentActivity | None") -> bool:
        """Whether nothing but the time differs."""
        return other is not None and (
            (self.state, self.replies, self.tasks, self.listening_rooms, self.quiet)
            == (other.state, other.replies, other.tasks, other.listening_rooms, other.quiet)
        )
