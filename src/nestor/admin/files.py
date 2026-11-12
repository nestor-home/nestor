"""Files the admin hands out, as they were sent to Nestor: they must never run in the admin's origin."""

from urllib.parse import quote

from fastapi import Response

from nestor.modules.channels import IMAGE_TYPES


def file_response(data: bytes, media_type: str, name: str) -> Response:
    """`data` named `name`. Pictures and recordings open in place; anything else is downloaded, never shown, so a
    page or a script sent to Nestor cannot run here. Content-addressed, so cached for a day."""
    inline = media_type in IMAGE_TYPES or media_type.startswith("audio/")
    headers = {
        "Cache-Control": "private, max-age=86400, immutable",
        "Content-Disposition": _disposition("inline" if inline else "attachment", name),
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(data, media_type=media_type if inline else "application/octet-stream", headers=headers)


def _disposition(kind: str, name: str) -> str:
    """As Starlette's `FileResponse` writes it (RFC 6266): the plain name when it is safe as is, else encoded."""
    quoted = quote(name)
    return f'{kind}; filename="{name}"' if quoted == name else f"{kind}; filename*=utf-8''{quoted}"
