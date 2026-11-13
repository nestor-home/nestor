"""What Anthropic's Messages API takes: the system blocks, the dialogue, the tools, the effort."""

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from nestor.adapters.models.common import base64_of, turns
from nestor.core import ContractError
from nestor.modules.cognition import (
    Message,
    Role,
    ToolSpec,
)

type Block = dict[str, Any]

CACHED_LAYERS = 3  # of the 4 cache breakpoints a request may set: the last one caches the conversation
EPHEMERAL = {"type": "ephemeral"}


class Effort(StrEnum):
    """How much Claude thinks before answering (`output_config.effort`): less is faster and cheaper."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


def wire_system(messages: Sequence[Message]) -> list[Block]:
    """The system messages as system blocks: each stable layer marked for the cache (the first `CACHED_LAYERS`), the
    content after them.
    """
    blocks: list[Block] = []
    for message in messages:
        if message.role is not Role.SYSTEM:
            continue
        for position, layer in enumerate(message.layers):
            if layer:
                marked = position < CACHED_LAYERS
                blocks.append({"type": "text", "text": layer, **({"cache_control": EPHEMERAL} if marked else {})})
        if message.content:
            blocks.append({"type": "text", "text": message.content})
    return blocks


def wire_messages(messages: Sequence[Message], provider: str) -> list[Block]:
    """The dialogue in Anthropic's shape (`turns`): tool results are user blocks."""
    wired = turns(
        messages,
        lambda m: _blocks(m, provider),
        answer="assistant",
        result=lambda block: block["type"] == "tool_result",
    )
    return [{"role": role, "content": blocks} for role, blocks in wired]


def _blocks(message: Message, provider: str) -> list[Block]:
    match message.role:
        case Role.TOOL:
            if message.tool_call_id is None:
                raise ContractError(f"{provider}: a tool message must say which call it answers (tool_call_id)")
            result: Block = {"type": "tool_result", "tool_use_id": message.tool_call_id}
            return [result | ({"content": message.content} if message.content else {})]
        case Role.ASSISTANT:
            # the reasoning first, as Claude wrote it before its words and calls
            reasoning = [block for c in message.tool_calls if c.replay for block in json.loads(c.replay)]
            text = [{"type": "text", "text": message.content}] if message.content.strip() else []
            calls = [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": dict(c.arguments)} for c in message.tool_calls
            ]
            return [*reasoning, *text, *calls]
        case _:
            documents = [
                {"type": "document", "source": _base64(d.media_type, d.data), **({"title": d.name} if d.name else {})}
                for d in message.documents
            ]
            images = [{"type": "image", "source": _base64(i.media_type, i.data)} for i in message.images]
            text = [{"type": "text", "text": message.content}] if message.content.strip() else []
            return [*documents, *images, *text]


def _base64(media_type: str, data: bytes) -> dict[str, str]:
    return {"type": "base64", "media_type": media_type, "data": base64_of(data)}


def wire_tool(tool: ToolSpec) -> dict[str, object]:
    return {"name": tool.name, "description": tool.description, "input_schema": dict(tool.parameters)}
