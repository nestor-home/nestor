"""What the model adapters share: the hosted providers the OpenAI-compatible ones know (each requires a key), tool
calls streamed in fragments, files encoded once, and the dialogue as the turns of a native API."""

import base64
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from nestor.adapters.common.http import MAX_DETAIL, Failure, host_among
from nestor.core import new_id
from nestor.modules.cognition import Message, Role, ToolCall
from nestor.runtime.plugins import AdapterSettings

BRANDS = {  # host suffix → brand; published in `base_url`'s schema (`x-nestor.brands`) so the admin shows the same
    "openrouter.ai": "openrouter",
    "openai.com": "openai",
    "mistral.ai": "mistral",
    "anthropic.com": "anthropic",
    "generativelanguage.googleapis.com": "gemini",
    "groq.com": "groq",
}
BRANDED: dict[str, Any] = {"brands": BRANDS}  # the field the brand is read from


def brand_host(base_url: str) -> str | None:
    """The known provider `base_url` belongs to (`openrouter.ai`), if any: each requires an API key."""
    return host_among(base_url, BRANDS)


def brand(base_url: str) -> str | None:
    return BRANDS.get(brand_host(base_url) or "")


class EndpointSettings(AdapterSettings):
    """An OpenAI-compatible endpoint; `api_key` should come from the environment.

    The key is optional, as local servers need none: empty is the same as absent. The hosted providers known
    to require one refuse to be configured without it."""

    base_url: str = Field(json_schema_extra=BRANDED)
    api_key: SecretStr | None = Field(default=None, validate_default=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_is_absent(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("api_key")
    @classmethod
    def _required_by_known_providers(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        if value is None and (host := brand_host(str(info.data.get("base_url", "")))):
            raise PydanticCustomError("api_key_required", "{host} requires an API key", {"host": host})
        return value


@dataclass(slots=True)
class PartialCall:
    """A tool call streamed in fragments: its arguments come as pieces of JSON."""

    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)
    replay: str | None = None

    def call(self, error: Failure) -> ToolCall:
        """The call once its stream is over; a nameless one, or arguments that are not a JSON object, are `error`."""
        if not self.name:
            raise error("a tool call has no name", transient=True)
        raw = "".join(self.arguments) or "{}"
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError:
            arguments = None
        if not isinstance(arguments, dict):
            raise error(f"tool call {self.name!r} has invalid JSON arguments: {raw[:MAX_DETAIL]}", transient=True)
        return ToolCall(self.id or new_id(), self.name, arguments, replay=self.replay)


@lru_cache(maxsize=8)
def base64_of(data: bytes) -> str:
    """`data` in base64: a file goes again with every round of a turn, and is encoded once."""
    return base64.b64encode(data).decode()


def turns[P](
    messages: Sequence[Message], parts: Callable[[Message], list[P]], *, answer: str, result: Callable[[P], bool]
) -> list[tuple[str, list[P]]]:
    """The dialogue as the turns of a native API (Anthropic, Gemini): system messages left out (they go apart), the
    model's own under the role `answer` and the others as `user`, the results of one round of tool calls together in
    one turn (as many as the calls, as the model asked for them), and opening on a person's words, as a window of the
    history may not."""
    wired: list[tuple[str, list[P]]] = []
    for message in messages:
        if message.role is Role.SYSTEM or not (wire := parts(message)):
            continue
        role = answer if message.role is Role.ASSISTANT else "user"
        if wired and wired[-1][0] == role and message.role is Role.TOOL:
            wired[-1][1].extend(wire)
        else:
            wired.append((role, wire))
    while wired and (wired[0][0] != "user" or result(wired[0][1][0])):
        wired.pop(0)
    return wired
