"""What Gemini's API takes: the dialogue as contents and parts, the tools as function declarations."""

from collections.abc import Mapping, Sequence
from typing import Any

from nestor.adapters.models.common import base64_of, turns
from nestor.core import ContractError
from nestor.modules.cognition import (
    Message,
    Role,
    ToolSpec,
)

type Part = dict[str, Any]

# the signature Gemini documents for a call it did not make in this turn (one asked through another model, before a
# fallback): without one, Gemini 3 refuses the turn
UNSIGNED = "skip_thought_signature_validator"


def wire_contents(messages: Sequence[Message], provider: str) -> list[dict[str, object]]:
    """The dialogue in Gemini's shape (`turns`): its own answers are the `model` role, tool results are `user` parts
    named for the call they answer, with its id.
    """
    names = {c.id: c.name for m in messages for c in m.tool_calls}
    wired = turns(
        messages,
        lambda m: _parts(m, names, provider),
        answer="model",
        result=lambda part: "functionResponse" in part,
    )
    return [{"role": role, "parts": parts} for role, parts in wired]


def _parts(message: Message, names: Mapping[str, str], provider: str) -> list[Part]:
    match message.role:
        case Role.TOOL:
            call = message.tool_call_id or ""
            if call not in names:
                raise ContractError(f"{provider}: a tool message must answer a call of the dialogue (tool_call_id)")
            return [{"functionResponse": {"id": call, "name": names[call], "response": {"result": message.content}}}]
        case Role.ASSISTANT:
            text = [{"text": message.content}] if message.content.strip() else []
            calls = [
                {
                    "functionCall": {"id": c.id, "name": c.name, "args": dict(c.arguments)},
                    "thoughtSignature": c.replay or UNSIGNED,
                }
                for c in message.tool_calls
            ]
            return [*text, *calls]
        case _:
            files = [*message.documents, *message.images]
            inline = [{"inlineData": {"mimeType": f.media_type, "data": base64_of(f.data)}} for f in files]
            text = [{"text": message.content}] if message.content.strip() else []
            return [*inline, *text]


def wire_tool(tool: ToolSpec) -> dict[str, object]:
    return {"name": tool.name, "description": tool.description, "parametersJsonSchema": dict(tool.parameters)}
