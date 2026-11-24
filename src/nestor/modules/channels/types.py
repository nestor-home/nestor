"""Values exchanged with channels: where a message comes from, who sent it, what it carries."""

import codecs
import mimetypes
import posixpath
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nestor.core import ContractError, PersonId, SessionId, new_id, utc_now
from nestor.modules.identity import Heard


class Medium(StrEnum):
    """How a turn travels, typed or said: it decides the answer's form (length, no Markdown when
    spoken), and how long a conversation lasts without a turn. A channel may carry both (a satellite
    with a screen and a microphone)."""

    SPOKEN = "spoken"
    WRITTEN = "written"

    @property
    def conversation_ends_after_s(self) -> float:
        """The silence after which the next turn opens a new conversation, unless a channel says otherwise.

        Spoken: 5 minutes, Home Assistant Assist's timeout; people speak in the moment and walk away.
        Written: 4 hours; a message chat is picked up again later in the day (after a meeting, after
        lunch), as a messaging thread is. A night's sleep is longer, so the next morning opens a new
        conversation without any clock rule.
        """
        return 300.0 if self is Medium.SPOKEN else 4 * 3600.0


@dataclass(frozen=True, slots=True)
class Address:
    """A conversation on a channel: `telegram:123456789`, `voice:living-room`.

    `channel` is the configured channel name, not the adapter kind: two Telegram bots are two channels.
    """

    channel: str
    conversation: str

    def __str__(self) -> str:
        return f"{self.channel}:{self.conversation}"

    @classmethod
    def parse(cls, text: str) -> "Address":
        channel, sep, conversation = text.partition(":")
        if not (sep and channel and conversation):
            raise ContractError(f"invalid address {text!r}, expected 'channel:conversation'")
        return cls(channel, conversation)

    @property
    def session(self) -> SessionId:
        """One session per conversation, whoever speaks in it (a group chat is one session)."""
        return SessionId(str(self))


@dataclass(frozen=True, slots=True, kw_only=True)
class Exchange:
    """Where an effect belongs in the dialogue, as Home Assistant's Assist counts it.

    `conversation_id` groups the turns of one session that follow each other closely: it ends after a
    while without any (`Channel.conversation_ends_after_s`). `turn_id` is one message and all it caused (tool
    calls, memories, tasks, the reply), or one unprompted message.
    """

    conversation_id: str
    turn_id: str


@dataclass(frozen=True, slots=True)
class Sender:
    """The author as the channel knows them; the runtime maps `id` to a person of the household through their accounts,
    unless the channel signed the person in itself and names them (`person`: the admin's chat)."""

    id: str
    name: str | None = None
    person: PersonId | None = None


def base_type(media_type: str) -> str:
    """A media type without its parameters, lower-cased: `text/plain; charset=utf-8` is `text/plain`."""
    return media_type.split(";")[0].strip().lower()


def plain_name(name: str | None, media_type: str) -> str:
    """The name a person sees a file by: its own, without any folder (it may be written in one), else its kind with
    its type's extension (`file.pdf`, `image.png`)."""
    plain = posixpath.basename((name or "").replace("\\", "/")).strip(" .")
    base = base_type(media_type)
    return plain or f"{AttachmentKind.of(base)}{mimetypes.guess_extension(base) or ''}"


class AttachmentKind(StrEnum):
    """What a file sent along a message is, as the person meant it."""

    IMAGE = "image"
    VOICE = "voice"  # a message recorded to be listened to, in place of typing
    AUDIO = "audio"  # an audio file (music, a recording)
    FILE = "file"  # anything else (a PDF, a spreadsheet)

    @classmethod
    def of(cls, media_type: str) -> "AttachmentKind":
        """What a file made by Nestor is, from its type: a picture, an audio file, or another file."""
        base = base_type(media_type)
        return cls.IMAGE if base in IMAGE_TYPES else cls.AUDIO if base.startswith("audio/") else cls.FILE


IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})  # what models and browsers show


@dataclass(frozen=True, slots=True, kw_only=True)
class Attachment:
    """A file sent with a message, or with an answer: its bytes, as the channel received or will send them."""

    kind: AttachmentKind
    data: bytes = field(repr=False)
    media_type: str
    name: str | None = None

    @property
    def file_name(self) -> str:
        """The name a person sees it by (`plain_name`)."""
        return plain_name(self.name, self.media_type)


@dataclass(frozen=True, slots=True, kw_only=True)
class InboundMessage:
    """A message to the assistant. `sender` is the account the channel authenticated; `None` on a shared device (a
    satellite), which vouches for the place only: whoever is there may speak. `heard` is what their voice told,
    when it was said and voices are recognised. `text` may be empty when `attachments` carry the message (a photo
    without a caption, a voice message)."""

    address: Address
    sender: Sender | None
    text: str
    medium: Medium = Medium.WRITTEN  # typed or said: the answer takes the same way
    attachments: tuple[Attachment, ...] = ()
    heard: Heard | None = None
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)


# what a channel announces when it does not know: the file is identified by its content and its name instead
UNKNOWN_TYPES = frozenset(
    {"", "application/octet-stream", "application/binary", "binary/octet-stream", "application/x-binary"}
)
PDF = "application/pdf"
# Python's own table of extensions, the same on every machine (the system's files name `.ts` a Qt translation on Linux)
_BY_NAME = mimetypes.MimeTypes()
SNIFFED = 4096  # bytes looked at to tell a file's type
_MAGIC = (  # what the first bytes of a file show it is
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)


def identified(media_type: str, name: str | None, data: bytes, *, reads: Callable[[str], bool]) -> str:
    """What a file is: `media_type`, as its channel announced it, unless that says nothing (`application/octet-stream`);
    then what its content shows (a picture, a PDF, text), text typed by its name when `reads` reads that type as text
    (`.json`), and what its name says for the rest."""
    if base_type(media_type) not in UNKNOWN_TYPES:
        return media_type
    head = data[:SNIFFED]
    if found := next((kind for magic, kind in _MAGIC if head.startswith(magic)), None):
        return found
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if b"%PDF-" in head[:1024]:  # readers accept a few bytes before the header
        return PDF
    named = _BY_NAME.guess_type(name, strict=False)[0] if name else None
    if _text(head):  # a name types it only as text: a `.ts` source is no MPEG stream, a `.pdf` of text is no PDF
        return named if named is not None and named != PDF and reads(named) else "text/plain"
    return named or "application/octet-stream"


def _text(head: bytes) -> bool:
    """Whether the first bytes of a file are text: UTF-8 without a NUL byte, a character cut at the end allowed."""
    if not head or b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head)
    except UnicodeDecodeError:
        return False
    return True
