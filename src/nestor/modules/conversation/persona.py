"""The agent's persona and the instructions built from it for each turn."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.core.i18n import Locale, Message
from nestor.modules.channels import Medium
from nestor.modules.conversation.types import SILENT, FallbackReason
from nestor.modules.household import Person
from nestor.modules.identity import Identified, Speaker

SPOKEN = """Everything you write is spoken aloud. Answer briefly: one or two sentences unless asked to explain.
Start with a very short sentence (three to six words): the voice only starts once it is complete.
Never use Markdown, lists, URLs or emoji."""

WRITTEN = """You are writing in a chat. Be concise and natural; light formatting only when it helps."""

ENGLISH = Locale("en")

HONESTY = """Never claim something was done without its result. If you cannot do something, say so plainly."""

NOTIFICATIONS = """Some messages come from Nestor itself, marked [From Nestor itself, …]: a task's result, a watch, a \
wake-up, a message to pass on. Answer one as a message of yours to the person it is for, unprompted: briefly, in your \
own words, never with internal identifiers. Do what it asks with your tools first: only your last message reaches \
them, so never announce what you are about to do."""

QUIET = f"""What opens this turn may go unanswered: if there is nothing they need to know (a check that found \
nothing), answer exactly {SILENT} and nothing else."""

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
        speaker: Speaker | None = None,
        room: str | None = None,
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
                NOTIFICATIONS,
                *guidance,
            ),
            household=_joined(f"The household: {names}." if names else "", *household),
            turn=_joined(
                f"Now: {local:%A %d %B %Y, %H:%M} ({self.timezone}).",
                _who(person, speaker, room),
                *turn,
            ),
        )

    def fallback(self, reason: FallbackReason) -> Message:
        return FALLBACKS[reason]


def _who(person: Person | None, speaker: Speaker | None, room: str | None) -> str:
    """Who speaks, and how anyone knows: the agent asks when it matters and nobody is known."""
    by = speaker.by if speaker else Identified.ACCOUNT
    if person is not None and by is Identified.VOICE:
        return f"You are talking with {person.name}, recognised by their voice."
    if person is not None and by is Identified.SAID:
        return f"You are talking with {person.name}, who said so; nothing confirms it."
    if person is not None:
        return f"You are talking with {person.name}."
    if room is not None:
        return f"Someone at home is talking to you through the satellite of the room {room}: you do not know who."
    return "You do not know who you are talking with."


def _joined(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
