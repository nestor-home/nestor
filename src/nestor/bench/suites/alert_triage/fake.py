"""A deterministic stand-in for the triage model, so the suite runs end to end without a network (CI, a first
try). It is a crude word-overlap judge, not a baseline worth beating: an alert matches when one of its
distinctive words is in the item.

    models: {fake: {type: language, provider: alert-triage-fake}}
"""

import json
import re
import unicodedata
from collections.abc import AsyncGenerator

from nestor.core import Unit, Usage, report
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    LanguageModel,
    ModelOutput,
    ModelRequest,
    Role,
    TextDelta,
)
from nestor.modules.system.selfmap import Card
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services

SERVED = "fake/word-overlap-1"
_LISTED = re.compile(r'^- \[(?P<id>[^\]]+)\] "(?P<what>.*)"$', re.MULTILINE)
_COMMON_WORDS = (
    "about tell when with from that this have will what which there their they your mine also anything something "
    "quand avec dans pour mais nous vous leur elle sont tout tous cette quelque chose dire envoie nouvelle"
)
_COMMON = frozenset(_COMMON_WORDS.split())


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _words(what: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", _fold(what)) if len(w) >= 4 and w not in _COMMON}


def _judge(what: str, item: str) -> bool:
    return any(word in item for word in _words(what))


class FakeTriageModel(LanguageModel):
    name = "alert-triage-fake"

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        system = next((m.content for m in request.messages if m.role is Role.SYSTEM), "")
        item = _fold(" ".join(m.content for m in request.messages if m.role is Role.USER))
        found = [{"alert": id, "summary": "-"} for id, what in _LISTED.findall(system) if _judge(what, item)]
        answer = json.dumps({"matches": found})
        yield TextDelta(answer)
        read = len(" ".join(m.content for m in request.messages).split())
        report(Usage({Unit.INPUT_TOKENS: read, Unit.OUTPUT_TOKENS: len(answer.split())}, served=SERVED))
        yield Finished(FinishReason.STOP)


class FakeSettings(AdapterSettings):
    """No setting: the fake answers the same thing to the same request, always."""


def _build(settings: FakeSettings, name: str, services: Services) -> FakeTriageModel:
    return FakeTriageModel()


plugin = Plugin(
    Family.MODEL,
    "alert-triage-fake",
    FakeSettings,
    _build,
    serves=LanguageModel,
    card=Card(
        summary="A deterministic stand-in for a triage model, to run the suite without a network.", docs="plugins"
    ),
)
