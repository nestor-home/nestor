"""Values exchanged with the conversation model: dialogue messages, tools and streamed output."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # set on TOOL messages: which call this result answers

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role=Role.USER, content=content)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool offered to the model; `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: Mapping[str, object] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallRequested:
    call: ToolCall


class FinishReason(StrEnum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"


@dataclass(frozen=True, slots=True)
class Finished:
    reason: FinishReason


type ModelOutput = TextDelta | ToolCallRequested | Finished
