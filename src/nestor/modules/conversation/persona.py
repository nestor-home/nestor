"""The agent's persona and the instructions built from it for each turn."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.core.i18n import Locale, Message
from nestor.modules.channels import Medium
from nestor.modules.conversation.types import FallbackReason
from nestor.modules.household import Person

SPOKEN = """Everything you write is spoken aloud. Answer briefly: one or two sentences unless asked to explain.
Start with a very short sentence (three to six words): the voice only starts once it is complete.
Never use Markdown, lists, URLs or emoji."""

WRITTEN = """You are writing in a chat. Be concise and natural; light formatting only when it helps."""

ENGLISH = Locale("en")

HONESTY = """Never claim something was done without its result. If you cannot do something, say so plainly."""

FALLBACKS: Mapping[FallbackReason, Message] = {
    FallbackReason.MODEL_UNAVAILABLE: Message.of("fallback-model-unavailable"),
    FallbackReason.MODEL_SLOW: Message.of("fallback-model-slow"),
    FallbackReason.RECOGNITION_UNAVAILABLE: Message.of("fallback-recognition-unavailable"),
    FallbackReason.SYNTHESIS_UNAVAILABLE: Message.of("fallback-synthesis-unavailable"),
}


@dataclass(frozen=True, slots=True)
class Instructions:
    """The instructions of a turn, from the most stable to the most variable: what never changes
    (who the agent is, its rules, how to use each module), what changes now and then (the household),
    and this turn's (the time, who speaks, what is going on)."""

    stable: str
    household: str
    turn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Persona:
    """Who the agent is. `character` is free text written by the distribution (Richie's personality)."""

    name: str
    character: str
    locale: Locale = ENGLISH  # BCP 47: the fixed phrases the assistant says (fallbacks…)
    language: str = "English"  # how the instructions name the language the model must write in
    timezone: str = "UTC"

    def instructions(
        self,
        *,
        medium: Medium,
        style: str,
        person: Person | None,
        now: datetime,
        guidance: tuple[str, ...] = (),
        people: tuple[Person, ...] = (),
        household: tuple[str, ...] = (),
        turn: tuple[str, ...] = (),
    ) -> Instructions:
        local = now.astimezone(ZoneInfo(self.timezone))
        names = ", ".join(p.name for p in people)
        return Instructions(
            stable=_joined(
                self.character.strip(),
                f"Always write in {self.language}, every sentence, including what you say before using a tool.",
                SPOKEN if medium is Medium.SPOKEN else WRITTEN,
                style.strip(),
                HONESTY,
                *guidance,
            ),
            household=_joined(f"The household: {names}." if names else "", *household),
            turn=_joined(
                f"Now: {local:%A %d %B %Y, %H:%M} ({self.timezone}).",
                f"You are talking with {person.name}." if person else "You do not know who you are talking with.",
                *turn,
            ),
        )

    def fallback(self, reason: FallbackReason) -> Message:
        return FALLBACKS[reason]


def _joined(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
