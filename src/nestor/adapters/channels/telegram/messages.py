"""What the Bot API's `getUpdates` brings: updates, their messages and the files these carry."""

from pydantic import BaseModel, Field, TypeAdapter

from nestor.modules.channels import IMAGE_TYPES, AttachmentKind


class _Chat(BaseModel):
    id: int


class User(BaseModel):
    id: int
    first_name: str | None = None


class File(BaseModel):
    """A file of a message (a photo size, a voice message, an audio file, a document), downloaded by `file_id`."""

    file_id: str
    file_size: int | None = None
    mime_type: str | None = None
    file_name: str | None = None


class Message(BaseModel):
    chat: _Chat
    sender: User | None = Field(default=None, alias="from")
    date: int
    text: str | None = None
    caption: str | None = None
    photo: list[File] = []  # the same picture in several sizes, the largest last
    voice: File | None = None
    audio: File | None = None
    document: File | None = None

    @property
    def has_files(self) -> bool:
        return bool(self.photo or self.voice or self.audio or self.document)

    def files(self) -> list[tuple[AttachmentKind, File, str]]:
        """Its files, each with its kind and media type: the largest size of a photo, a document that is an image
        as an image."""
        found: list[tuple[AttachmentKind, File, str]] = []
        if self.photo:
            found.append((AttachmentKind.IMAGE, self.photo[-1], "image/jpeg"))
        if self.voice:
            found.append((AttachmentKind.VOICE, self.voice, self.voice.mime_type or "audio/ogg"))
        if self.audio:
            found.append((AttachmentKind.AUDIO, self.audio, self.audio.mime_type or "audio/mpeg"))
        if self.document:
            media_type = self.document.mime_type or "application/octet-stream"
            kind = AttachmentKind.IMAGE if media_type in IMAGE_TYPES else AttachmentKind.FILE
            found.append((kind, self.document, media_type))
        return found


class Update(BaseModel):
    update_id: int
    message: Message | None = None


UPDATES = TypeAdapter(list[Update])
