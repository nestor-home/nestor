"""The admin's chats as the front reads them: each chat, its messages and the tools called on the way, built from the
journal; what is sent, and the answer as it is written."""

import base64
import binascii
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nestor.adapters.channels.web import Ended, Failed, Part, Written
from nestor.admin.presentation import Phrasebook, subject
from nestor.core import Event
from nestor.core.i18n import Message
from nestor.modules.channels import AttachmentKind
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted, ToolDeferred, ToolReturned
from nestor.modules.conversation import (
    AnswerVoiced,
    AssistantTurn,
    Attached,
    FallbackSpoken,
    NotificationTurn,
    UserTurn,
)
from nestor.modules.journal import Entry

TURNS = frozenset({UserTurn.event_type, NotificationTurn.event_type, AssistantTurn.event_type})
THREAD = TURNS | {
    e.event_type for e in (AnswerVoiced, FallbackSpoken, ToolCalled, ToolCompleted, ToolDeferred, ToolReturned)
}
TITLE_LENGTH = 80
FILE_LIMIT = 20 * 1024 * 1024  # what a message may carry, per file, as a messaging app takes it


class ChatOut(BaseModel):
    id: str
    title: str  # the first words written in it; empty when it opened with files only
    files: list[AttachmentKind]  # what the first message carried, to name a chat without words
    started_at: datetime
    updated_at: datetime
    answering: bool  # an answer is being written in it now


class ChatsOut(BaseModel):
    chats: list[ChatOut]  # the latest first
    sessions: str  # what the journal's session of each of these chats starts with, then its id


class MentionOut(BaseModel):
    """What a message can name with `@`: an executor to hand work to."""

    name: str
    description: str
    brand: str | None


class ChatRole(StrEnum):
    PERSON = "person"  # what the person wrote or said
    ASSISTANT = "assistant"
    NOTE = "note"  # what Nestor brought in by itself (a task's result), before its answer
    FALLBACK = "fallback"  # the assistant could not answer and said so
    TOOL = "tool"


class ToolState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BACKGROUND = "background"  # goes on after the turn; its result comes back in the chat


class ChatFileOut(BaseModel):
    """A file of a message; its bytes at `/journal/{position}/attachments/{index}`."""

    position: int
    index: int
    kind: AttachmentKind
    media_type: str
    size: int
    name: str | None
    transcript: str | None

    @classmethod
    def of(cls, position: int, index: int, attached: Attached) -> "ChatFileOut":
        blob = attached.blob
        return cls(
            position=position,
            index=index,
            kind=attached.kind,
            media_type=blob.media_type,
            size=blob.size,
            name=attached.name,
            transcript=attached.transcript,
        )


class ChatToolOut(BaseModel):
    call: str
    name: str
    state: ToolState
    arguments: dict[str, Any]
    output: str | None  # what the model received, once it answered
    duration_s: float | None


class ChatMessageOut(BaseModel):
    position: int
    id: str
    at: datetime
    role: ChatRole
    turn: str | None
    text: str  # a note: what it is about, in the reader's language
    files: list[ChatFileOut]
    interrupted: bool  # stopped before its end
    tool: ChatToolOut | None  # a `tool` message only


class ChatThreadOut(BaseModel):
    chat: str
    session: str  # the chat's session in the journal: its live entries name it
    messages: list[ChatMessageOut]  # oldest first
    answering: bool


def chats(entries: Sequence[Entry], under: str, answering: frozenset[str]) -> list[ChatOut]:
    """Every chat that has a turn, from the turns of a person's chats (`under`: what their sessions start with)."""
    found: dict[str, ChatOut] = {}
    for entry in entries:
        event = entry.event()
        chat = str(event.session).removeprefix(under)
        seen = found.get(chat)
        if seen is not None:
            seen.updated_at = event.at
            continue
        words = event.text if isinstance(event, UserTurn) else ""
        files = [a.kind for a in event.attachments] if isinstance(event, UserTurn) else []
        found[chat] = ChatOut(
            id=chat,
            title=_title(words),
            files=files,
            started_at=event.at,
            updated_at=event.at,
            answering=chat in answering,
        )
    return sorted(found.values(), key=lambda c: c.updated_at, reverse=True)


def thread(entries: Sequence[Entry], words: Phrasebook) -> list[ChatMessageOut]:
    """A chat's messages in the order they were written, each tool call where it was made."""
    messages: list[ChatMessageOut] = []
    answers: dict[str, ChatMessageOut] = {}
    calls: dict[str, ChatToolOut] = {}
    for entry in entries:
        event = entry.event()
        match event:
            case UserTurn():
                said = [a.transcript for a in event.attachments if a.kind is AttachmentKind.VOICE and a.transcript]
                text = event.text.removesuffix("\n".join(said)).strip() if said else event.text
                files = [ChatFileOut.of(entry.position, i, a) for i, a in enumerate(event.attachments)]
                messages.append(_message(entry, event, ChatRole.PERSON, text, files=files))
            case NotificationTurn():
                note = words.text(Message("journal-subject", subject(event.about)))
                messages.append(_message(entry, event, ChatRole.NOTE, note))
            case AssistantTurn():
                answer = _message(entry, event, ChatRole.ASSISTANT, event.text, interrupted=event.interrupted)
                answers[event.id] = answer
                messages.append(answer)
            case AnswerVoiced():
                if (answer := answers.get(event.answer)) is not None:
                    answer.files.append(ChatFileOut.of(entry.position, 0, event.voice))
            case FallbackSpoken():
                said = words.text(Message.of("journal-fallback", reason=event.reason))
                messages.append(_message(entry, event, ChatRole.FALLBACK, said))
            case ToolCalled() | ToolDeferred():
                call = calls.get(event.call_id)
                if call is None:
                    call = calls[event.call_id] = ChatToolOut(
                        call=event.call_id,
                        name=event.name,
                        state=ToolState.RUNNING,
                        arguments=dict(event.arguments),
                        output=None,
                        duration_s=None,
                    )
                    messages.append(_message(entry, event, ChatRole.TOOL, "", tool=call))
                if isinstance(event, ToolDeferred):
                    call.state = ToolState.BACKGROUND
            case ToolCompleted() | ToolReturned():
                if (call := calls.get(event.call_id)) is not None:
                    call.state = ToolState.DONE if event.ok else ToolState.FAILED
                    call.output, call.duration_s = event.output, event.duration_s
    return messages


def _message(
    entry: Entry,
    event: Event,
    role: ChatRole,
    text: str,
    *,
    files: list[ChatFileOut] | None = None,
    interrupted: bool = False,
    tool: ChatToolOut | None = None,
) -> ChatMessageOut:
    exchange = getattr(event, "exchange", None)
    return ChatMessageOut(
        position=entry.position,
        id=event.id,
        at=event.at,
        role=role,
        turn=exchange.turn_id if exchange else None,
        text=text,
        files=files or [],
        interrupted=interrupted,
        tool=tool,
    )


def _title(words: str) -> str:
    line = " ".join(words.split())
    return line if len(line) <= TITLE_LENGTH else line[: TITLE_LENGTH - 1].rstrip() + "…"


class ChatFileIn(BaseModel):
    kind: AttachmentKind  # `voice` for a message recorded in the page; the others as the file is
    media_type: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=255)
    data: str  # base64

    @field_validator("data")
    @classmethod
    def _decodes(cls, data: str) -> str:
        try:
            size = len(base64.b64decode(data, validate=True))
        except binascii.Error:
            raise ValueError("data must be base64") from None
        if size == 0 or size > FILE_LIMIT:
            raise ValueError(f"a file holds between 1 byte and {FILE_LIMIT // (1024 * 1024)} MB")
        return data


class ChatMessageIn(BaseModel):
    text: str = Field(default="", max_length=32_000)
    files: list[ChatFileIn] = Field(default=[], max_length=10)

    @model_validator(mode="after")
    def _says_something(self) -> "ChatMessageIn":
        if not (self.text.strip() or self.files):
            raise ValueError("write something, or send a file")
        return self


class ChatStreamOut(BaseModel):
    """One line of an answer's stream: `text` words of the message being written, `end` that message complete
    (`last`: no other follows), `failed` the answer broke off, `done` the stream is over."""

    type: Literal["text", "end", "failed", "done"]
    text: str | None = None
    last: bool | None = None

    @classmethod
    def of(cls, part: Part) -> "ChatStreamOut":
        match part:
            case Written(text):
                return cls(type="text", text=text)
            case Ended(last):
                return cls(type="end", last=last)
            case Failed():
                return cls(type="failed")
