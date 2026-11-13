"""The OpenAI API's wire format: Chat Completions messages and tools encoded, the pictures and recordings it takes or
gives. Its streamed answers are decoded in `stream`."""

import json
from enum import StrEnum
from typing import Any

from nestor.adapters.models.common import base64_of
from nestor.core import ContractError
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition import (
    Image,
    Message,
    Role,
    ToolCall,
    ToolSpec,
)

SIGNATURES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF8": "image/gif"}


class ImageEndpoint(StrEnum):
    IMAGES = "images"  # POST /images/generations
    CHAT = "chat"  # POST /chat/completions with `modalities`


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
            pictures = [{"type": "image_url", "image_url": {"url": _data_url(i)}} for i in message.images]
            return {"role": "user", "content": [{"type": "text", "text": message.text}, *pictures]}
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
