"""Asking a model for a whole answer, text or JSON: the side calls that sort, summarize or title (alerts, memory,
conversations), not the agent."""

import json
from typing import Any

from nestor.modules.cognition.model.ports import LanguageModel
from nestor.modules.cognition.model.types import ModelRequest, TextDelta


async def text_answer(model: LanguageModel, request: ModelRequest) -> str:
    """What the model writes, whole. A provider failure raises `ProviderError`."""
    return "".join([o.text async for o in model.stream(request) if isinstance(o, TextDelta)])


async def json_answer(model: LanguageModel, request: ModelRequest) -> dict[str, Any] | None:
    """The JSON object the model answers with (`json_object`); `None` when there is none. A provider failure raises
    `ProviderError`."""
    return json_object(await text_answer(model, request))


def json_object(text: str) -> dict[str, Any] | None:
    """The JSON object a model wrote, found between its first `{` and its last `}` (small models and agents wrap it
    in prose or a code fence); `None` when there is none."""
    start, end = text.find("{"), text.rfind("}")
    try:
        found = json.loads(text[start : end + 1]) if 0 <= start < end else None
    except json.JSONDecodeError:
        return None
    return found if isinstance(found, dict) else None
