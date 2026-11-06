"""Asking a model for a JSON answer: the side calls that sort or summarize (watches, memory), not the agent."""

import json
from typing import Any

from nestor.modules.cognition.model.ports import LanguageModel
from nestor.modules.cognition.model.types import ModelRequest, TextDelta


async def json_answer(model: LanguageModel, request: ModelRequest) -> dict[str, Any] | None:
    """The JSON object the model answers with, found between its first `{` and its last `}` (small models wrap
    it in prose or a code fence); `None` when there is none. A provider failure raises `ProviderError`."""
    text = "".join([o.text async for o in model.stream(request) if isinstance(o, TextDelta)])
    start, end = text.find("{"), text.rfind("}")
    try:
        answer = json.loads(text[start : end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    return answer if isinstance(answer, dict) else None
