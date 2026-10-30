"""An RFC 5322 message (as IMAP hands it) as readable values: decoded headers and a plain-text body.

The body is the part `email` picks as the message body, plain text first, HTML flattened to text
otherwise. A message cut at the fetch size limit still parses: its tail is simply missing.
"""

from dataclasses import dataclass
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser

from nestor.adapters.connectors.common import decode_header_value, html_to_text, tidy


@dataclass(frozen=True, slots=True, kw_only=True)
class MailMessage:
    subject: str
    sender: str
    to: str
    date: str
    body: str
    attachments: tuple[str, ...]

    @classmethod
    def parse(cls, raw: bytes) -> "MailMessage":
        message = BytesParser(policy=policy.default).parsebytes(raw)
        return cls(
            subject=_header(message, "subject") or "(no subject)",
            sender=_header(message, "from"),
            to=_header(message, "to"),
            date=_header(message, "date"),
            body=_body(message),
            attachments=tuple(name for p in message.iter_attachments() if (name := p.get_filename())),
        )


def _header(message: Message, name: str) -> str:
    value = message.get(name)
    return decode_header_value(str(value)) if value is not None else ""


def _body(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        text = str(part.get_content())
    except (LookupError, ValueError):  # unknown charset, broken encoding
        payload = part.get_payload(decode=True)
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else ""
    return html_to_text(text) if part.get_content_subtype() == "html" else tidy(text)
