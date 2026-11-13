"""The OpenAI chat completions format: what a client's request says, and the answer as OpenAI writes it, whole or
streamed."""

import base64
import binascii
import hashlib
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi.responses import JSONResponse

from nestor.core import new_id
from nestor.modules.channels import IMAGE_TYPES, Attachment, AttachmentKind, MessageEnd, Reply

MODEL = "nestor"  # the one model it serves


def last_user_message(messages: list[Mapping[str, Any]]) -> tuple[str, tuple[Attachment, ...]]:
    """The words and pictures of the last message the person wrote; the client's history before it is Nestor's to
    keep, not the client's."""
    last = next(m for m in reversed(messages) if m.get("role") == "user")
    content = last.get("content")
    if isinstance(content, str):
        return content, ()
    words, pictures = [], []
    for part in content if isinstance(content, list) else []:
        if part.get("type") == "text":
            words.append(str(part.get("text", "")))
        elif part.get("type") == "image_url" and (picture := _picture(str(part["image_url"]["url"]))):
            pictures.append(picture)
    return "\n".join(words), tuple(pictures)


def thread(messages: list[Mapping[str, Any]]) -> str:
    """Which of the client's threads a request continues, from the first message the person wrote in it: a new chat in
    the client is a new conversation for Nestor too."""
    first = next(m for m in messages if m.get("role") == "user")
    return hashlib.sha256(json.dumps(first.get("content"), ensure_ascii=False).encode()).hexdigest()[:16]


def _picture(url: str) -> Attachment | None:
    """A picture sent inline (`data:image/png;base64,…`); one given by address is not fetched."""
    header, _, data = url.partition(",")
    media_type = header.removeprefix("data:").split(";")[0]
    if not header.startswith("data:") or media_type not in IMAGE_TYPES:
        return None
    try:
        return Attachment(kind=AttachmentKind.IMAGE, data=base64.b64decode(data, validate=True), media_type=media_type)
    except (binascii.Error, ValueError):
        return None


async def whole(reply: Reply) -> str:
    """The answer's messages, a blank line between two."""
    return "\n\n".join([message async for message in reply.messages()])


async def stream(reply: Reply) -> AsyncIterator[str]:
    """Server-sent events as OpenAI streams them: a chunk per piece written, a blank line between two messages, the
    end, then `[DONE]`."""
    identity, created = f"chatcmpl-{new_id()}", int(time.time())
    written = False

    def chunk(delta: Mapping[str, Any], finish: str | None = None) -> str:
        choice = {"index": 0, "delta": dict(delta), "finish_reason": finish}
        payload = {"id": identity, "object": "chat.completion.chunk", "created": created, "model": MODEL}
        return f"data: {json.dumps(payload | {'choices': [choice]}, ensure_ascii=False)}\n\n"

    yield chunk({"role": "assistant", "content": ""})
    async for part in reply:
        if isinstance(part, MessageEnd):
            if written and not part.last:
                yield chunk({"content": "\n\n"})
            continue
        written = written or bool(part.strip())
        yield chunk({"content": part})
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def completion(text: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{new_id()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def model() -> dict[str, Any]:
    return {"id": MODEL, "object": "model", "created": 0, "owned_by": "nestor"}


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": code, "code": code}}, status_code=status)
