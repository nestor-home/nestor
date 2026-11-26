"""The map of Nestor itself, built at start from the installed plugins and the configuration, and what of it answers a
question."""

import re
from collections.abc import Iterable, Sequence

from nestor.core import Health
from nestor.modules.system.selfmap.types import Capability, Part, Standing

RELEVANT = 6  # the parts a question gets in full
_WORD = re.compile(r"[a-z0-9]+")
_STEM = 5  # words compared on their first letters: "notified" finds "notifications"
_IGNORED = frozenset(  # words of any question
    re.findall(
        r"\w+",
        "the and for you your can could would with what how does into from that this are not use has have its any "
        "nestor",
    )
)


class SelfMap:
    """Every part Nestor knows of, plugged or not, in a stable order: plugged first, then installed, then missing."""

    def __init__(self, parts: Iterable[Part]) -> None:
        order = list(Standing)
        self.parts: tuple[Part, ...] = tuple(sorted(parts, key=lambda p: (order.index(p.standing), p.id)))

    def overview(self) -> str:
        """One line per capability: what is plugged, what is installed but not configured, what is missing."""
        lines = []
        for capability in Capability:
            parts = [p for p in self.parts if p.capability is capability]
            if not parts:
                continue
            said = []
            for standing in Standing:
                ids = [p.id for p in parts if p.standing is standing]
                said.append(f"{standing.value}: {', '.join(ids)}" if ids else f"{standing.value}: none")
            lines.append(f"- {capability.value}: {'; '.join(said)}")
        return "\n".join(lines)

    def relevant(self, question: str, *, limit: int = RELEVANT) -> Sequence[Part]:
        """The parts whose words the question shares the most, the best first; none when it shares none."""
        asked = _stems(question)
        scored = [(len(asked & _stems(_words_of(p))), p) for p in self.parts]
        ranked = sorted((s for s in scored if s[0]), key=lambda s: -s[0])  # stable: plugged first among equals
        return [part for _, part in ranked[:limit]]


def describe(part: Part) -> str:
    """A part for the model: what it is, where it stands here, what it needs and where it is documented."""
    if part.standing is Standing.PLUGGED:
        health = part.health()
        unwell = f", {health.value}" if health not in (None, Health.STARTED) else ""
        standing = f"plugged in as {', '.join(part.names)}{unwell}"
    elif part.standing is Standing.INSTALLED:
        standing = "installed, not configured"
    else:
        standing = f"not installed: {part.install}"
    needs = f" Needs: {', '.join(n.value for n in part.card.needs)}." if part.card.needs else ""
    return f"- {part.id} ({part.capability.value}; {standing}): {part.card.summary}{needs} Docs: {part.card.url}"


def _words_of(part: Part) -> str:
    return " ".join((part.id, part.capability.value, part.card.summary, part.card.docs))


def _stems(text: str) -> set[str]:
    return {w[:_STEM] for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _IGNORED}
