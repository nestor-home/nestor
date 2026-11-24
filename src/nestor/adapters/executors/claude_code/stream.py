"""Claude Code's `stream-json` as Nestor speaks it: the user messages it sends, the steps of the work and the report it
reads back."""

import json
from collections.abc import Mapping
from typing import Any

REPORTING = "StructuredOutput"  # the tool it ends with to give its report: not a step of the work

# What a step names: what the tool acts on. Never a shell command nor its description: the journal is read by the
# household, and a command may carry a secret.
SHOWN_INPUT = ("file_path", "path", "pattern", "query", "url")


def user_message(text: str) -> bytes:
    """One line of input: an instruction, as the person's message."""
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n").encode()


def tool_step(used: Mapping[str, Any]) -> str:
    given: Mapping[str, Any] = used["input"] if isinstance(used.get("input"), dict) else {}
    shown = next((str(given[key]) for key in SHOWN_INPUT if given.get(key)), None)
    return f"{used.get('name')}: {shown}" if shown else str(used.get("name"))
