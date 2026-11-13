"""What the webhook server reads of a request: its body, within a limit."""

from fastapi import Request


async def read_body(request: Request, limit: int) -> bytes | None:
    """The body, read up to `limit` bytes; `None` beyond, whatever `Content-Length` said."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)
