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
class Image:
    """A picture the model looks at with a message (a photo someone sent)."""

    media_type: str
    data: bytes = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    """A message of the dialogue. `layers` go before `content`, from the most stable: the same from
    one request to the next, so a provider that caches prompts may cache the request up to the end
    of each (the instructions' identity and rules, then the household)."""

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # set on TOOL messages: which call this result answers
    layers: tuple[str, ...] = ()
    images: tuple[Image, ...] = ()  # on USER messages, for a model that sees images (`LanguageModel.vision`)

    @classmethod
    def user(cls, content: str, images: tuple[Image, ...] = ()) -> "Message":
        return cls(role=Role.USER, content=content, images=images)

    @property
    def text(self) -> str:
        """Its layers and content, as one text."""
        return "\n\n".join(part for part in (*self.layers, self.content) if part)


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


@dataclass(frozen=True, slots=True, kw_only=True)
class Usage:
    """What a reply cost, as the provider reports it."""

    input_tokens: int
    output_tokens: int
    cost: float | None = None  # in the provider's billing currency, when it says
    cached_input_tokens: int | None = None  # of `input_tokens`, read from the provider's prompt cache


@dataclass(frozen=True, slots=True)
class Finished:
    reason: FinishReason
    usage: Usage | None = None  # when the provider reports it
    model: str | None = None  # the model that answered, as the provider names it (may differ from the one asked)


type ModelOutput = TextDelta | ToolCallRequested | Finished
