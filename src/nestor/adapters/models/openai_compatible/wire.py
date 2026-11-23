"""The OpenAI API's wire format: Chat Completions messages and tools encoded, the pictures and recordings it takes or
gives. Its streamed answers are decoded in `stream`."""

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from nestor.adapters.models.common import base64_of
from nestor.core import ContractError, Money, Unit, Usage
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import (
    Image,
    Message,
    Role,
    ToolCall,
    ToolSpec,
)

SIGNATURES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF8": "image/gif"}


SEEN = "[The pictures your tools just gave, for you to look at: not sent by anyone]"


class ImageEndpoint(StrEnum):
    IMAGES = "images"  # POST /images/generations
    CHAT = "chat"  # POST /chat/completions with `modalities`


def wire_messages(messages: Sequence[Message], provider: str, *, cache_control: bool) -> list[dict[str, object]]:
    """The dialogue in the chat completions' shape. A tool message carries text only: the pictures a round of calls
    gave follow its results, in a user message (`SEEN`)."""
    wired: list[dict[str, object]] = []
    seen: list[Image] = []
    for message in messages:
        if seen and message.role is not Role.TOOL:
            wired.append(_seen(seen))
            seen = []
        wired.append(wire_message(message, provider, cache_control=cache_control))
        if message.role is Role.TOOL:
            seen += message.images
    if seen:
        wired.append(_seen(seen))
    return wired


def _seen(images: Sequence[Image]) -> dict[str, object]:
    return {"role": "user", "content": [{"type": "text", "text": SEEN}, *map(_picture, images)]}


def wire_message(message: Message, provider: str, *, cache_control: bool) -> dict[str, object]:
    match message.role:
        case Role.ASSISTANT if message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": [_wire_call(c) for c in message.tool_calls],
            }
        case Role.TOOL:
            if message.tool_call_id is None:
                raise ContractError(f"{provider}: a tool message must say which call it answers (tool_call_id)")
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
        case Role.USER if message.images:
            return {"role": "user", "content": [{"type": "text", "text": message.text}, *map(_picture, message.images)]}
        case _ if cache_control and message.layers:
            parts: list[dict[str, object]] = [
                {"type": "text", "text": layer, "cache_control": {"type": "ephemeral"}}
                for layer in message.layers
                if layer
            ]
            if message.content:
                parts.append({"type": "text", "text": message.content})
            return {"role": message.role.value, "content": parts}
        case _:
            return {"role": message.role.value, "content": message.text}


def _picture(image: Image) -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": _data_url(image)}}


def _data_url(image: Image) -> str:
    return f"data:{image.media_type};base64,{base64_of(image.data)}"


def _wire_call(call: ToolCall) -> dict[str, object]:
    arguments = json.dumps(dict(call.arguments), ensure_ascii=False)
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": arguments}}


def wire_tool(tool: ToolSpec) -> dict[str, object]:
    function = {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)}
    return {"type": "function", "function": function}


def image(data: bytes, given: str | None, error: Any) -> Image:
    """`data` as a picture of a type people can see: its declared type, else the one its first bytes show."""
    media_type = (given or "").split(";")[0].strip().lower()
    if AttachmentKind.of(media_type) is not AttachmentKind.IMAGE:
        media_type = next((t for sig, t in SIGNATURES.items() if data.startswith(sig)), "")
        if not media_type and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            media_type = "image/webp"
    if not media_type:
        raise error("the picture is of a type that cannot be shown", transient=False)
    return Image(media_type=media_type, data=data)


def file_name(media_type: str) -> str:
    """A name whose extension tells the server the format, as some read it rather than the type."""
    base = media_type.split(";")[0].strip().lower()
    extension = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav", "audio/webm": "webm"}
    return f"recording.{extension.get(base, base.rpartition('/')[2] or 'bin')}"


def spent(usage: object, served: object = None, **more: float) -> Usage:
    """What an answer's `usage` says it consumed: Chat Completions and embeddings count `prompt_tokens` and
    `completion_tokens`, the image API `input_tokens` and `output_tokens`; OpenRouter adds what it billed (`cost`).
    `more`: units the answer itself shows (`images=1`)."""
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    units: dict[Unit, float] = {Unit(name): quantity for name, quantity in more.items()}
    for unit, value in (
        (Unit.INPUT_TOKENS, usage.get("prompt_tokens", usage.get("input_tokens"))),
        (Unit.OUTPUT_TOKENS, usage.get("completion_tokens", usage.get("output_tokens"))),
        (Unit.CACHED_INPUT_TOKENS, details.get("cached_tokens")),
        (Unit.CACHE_WRITE_TOKENS, details.get("cache_write_tokens")),
    ):
        if isinstance(value, int) and not isinstance(value, bool):
            units[unit] = value
    cost = usage.get("cost")
    billed = Money.usd(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None
    return Usage(units, billed, served if isinstance(served, str) and served else None)
