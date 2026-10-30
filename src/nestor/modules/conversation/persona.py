"""The agent's persona and the instructions built from it for each turn."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.modules.channels import Medium
from nestor.modules.conversation.types import FallbackReason
from nestor.modules.household import Person

SPOKEN = """Everything you write is spoken aloud. Answer briefly: one or two sentences unless asked to explain.
Start with a very short sentence (three to six words): the voice only starts once it is complete.
Never use Markdown, lists, URLs or emoji."""

WRITTEN = """You are writing in a chat. Be concise and natural; light formatting only when it helps."""

HONESTY = """Never claim something was done without its result. If you cannot do something, say so plainly."""

DEFAULT_FALLBACKS: Mapping[FallbackReason, str] = {
    FallbackReason.MODEL_UNAVAILABLE: "Désolé, j'ai un trou de connexion. Tu peux répéter ?",
    FallbackReason.MODEL_SLOW: "Hmm, je rame un peu, laisse-moi une seconde.",
    FallbackReason.RECOGNITION_UNAVAILABLE: "Je ne t'entends plus très bien, ma connexion fait des siennes.",
    FallbackReason.SYNTHESIS_UNAVAILABLE: "Ma voix a un souci, je reviens dès que possible.",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Persona:
    """Who the agent is. `character` is free text written by the distribution (Richie's personality)."""

    name: str
    character: str
    language: str = "French"
    timezone: str = "Europe/Paris"
    fallbacks: Mapping[FallbackReason, str] = field(default_factory=lambda: dict(DEFAULT_FALLBACKS))

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
            f"Always answer in {self.language}.",
            SPOKEN if medium is Medium.SPOKEN else WRITTEN,
            style.strip(),
            HONESTY,
            f"Now: {local:%A %d %B %Y, %H:%M} ({self.timezone}).",
            f"You are talking with {person.name}." if person else "You do not know who you are talking with.",
            *sections,
        ]
        return "\n\n".join(line for line in lines if line)

    def fallback(self, reason: FallbackReason) -> str:
        return self.fallbacks.get(reason) or DEFAULT_FALLBACKS[reason]
