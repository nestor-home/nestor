"""A Gmail message (`format=full`) as readable values: decoded headers and a plain-text body.

The body is every inline `text/plain` part in order; a mail without any falls back to its `text/html`
parts flattened to text. Attachments are listed by name, never read. Part data is base64url; it is
decoded with the charset its `Content-Type` declares (UTF-8 when absent or unknown).
"""

import base64
import binascii
import codecs
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from typing import Any

from nestor.adapters.connectors.common import decode_header_value, html_to_text, tidy


@dataclass(frozen=True, slots=True, kw_only=True)
class GmailMessage:
    id: str
    thread_id: str
    headers: Mapping[str, str]  # lower-case name → first value, decoded
    snippet: str
    received: datetime | None
    payload: Mapping[str, Any]

    @classmethod
    def of(cls, found: Mapping[str, Any]) -> "GmailMessage":
        payload = found.get("payload") or {}
        headers: dict[str, str] = {}
        for header in payload.get("headers", []):
            headers.setdefault(str(header.get("name", "")).lower(), decode_header_value(str(header.get("value", ""))))
        internal = str(found.get("internalDate", ""))
        return cls(
            id=str(found.get("id", "")),
            thread_id=str(found.get("threadId", "")),
            headers=headers,
            snippet=html_to_text(str(found.get("snippet", ""))),  # Gmail escapes snippets as HTML
            received=datetime.fromtimestamp(int(internal) / 1000, UTC) if internal.isdigit() else None,
            payload=payload,
        )

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")

    @property
    def subject(self) -> str:
        return self.header("subject") or "(no subject)"

    def text(self) -> str:
        plain = [_decoded(p) for p in _parts(self.payload) if _inline(p, "text/plain")]
        if any(plain):
            return tidy("\n\n".join(plain))
        return tidy("\n\n".join(html_to_text(_decoded(p)) for p in _parts(self.payload) if _inline(p, "text/html")))

    def attachments(self) -> list[str]:
        return [str(p["filename"]) for p in _parts(self.payload) if p.get("filename")]


def _parts(part: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield part
    for child in part.get("parts") or ():
        yield from _parts(child)


def _inline(part: Mapping[str, Any], mime_type: str) -> bool:
    body = part.get("body") or {}
    return str(part.get("mimeType", "")).lower() == mime_type and not part.get("filename") and "data" in body


def _decoded(part: Mapping[str, Any]) -> str:
    data = str(part["body"]["data"])
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError):
        return ""
    return raw.decode(_charset(part), errors="replace")


def _charset(part: Mapping[str, Any]) -> str:
    content_type = next(
        (str(h.get("value", "")) for h in part.get("headers", []) if str(h.get("name", "")).lower() == "content-type"),
        "",
    )
    parsed = Message()
    parsed["Content-Type"] = content_type
    charset = parsed.get_content_charset() or "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        return "utf-8"
    return charset
