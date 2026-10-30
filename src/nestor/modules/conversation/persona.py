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

HONESTY = """Never claim something was done without its result. If you cannot do something, say so plainly."""

FRENCH = Locale("fr-FR")

FALLBACKS: Mapping[FallbackReason, Message] = {
    FallbackReason.MODEL_UNAVAILABLE: Message.of("fallback-model-unavailable"),
    FallbackReason.MODEL_SLOW: Message.of("fallback-model-slow"),
    FallbackReason.RECOGNITION_UNAVAILABLE: Message.of("fallback-recognition-unavailable"),
    FallbackReason.SYNTHESIS_UNAVAILABLE: Message.of("fallback-synthesis-unavailable"),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Persona:
    """Who the agent is. `character` is free text written by the distribution (Richie's personality)."""

    name: str
    character: str
    locale: Locale = FRENCH  # BCP 47: the fixed phrases the assistant says (fallbacks…)
    language: str = "French"  # how the instructions name the language the model must write in
    timezone: str = "Europe/Paris"

    def instructions(
        self,
        *,
        medium: Medium,
        style: str,
        person: Person | None,
        now: datetime,
        sections: tuple[str, ...] = (),
    ) -> str:
        local = now.astimezone(ZoneInfo(self.timezone))
        lines = [
            self.character.strip(),
            f"Always write in {self.language}, every sentence, including what you say before using a tool.",
            SPOKEN if medium is Medium.SPOKEN else WRITTEN,
            style.strip(),
            HONESTY,
            f"Now: {local:%A %d %B %Y, %H:%M} ({self.timezone}).",
            f"You are talking with {person.name}." if person else "You do not know who you are talking with.",
            *sections,
        ]
        return "\n\n".join(line for line in lines if line)

    def fallback(self, reason: FallbackReason) -> Message:
        return FALLBACKS[reason]
