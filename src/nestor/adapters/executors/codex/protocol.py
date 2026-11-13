"""Codex's app-server as Nestor speaks to it: its command, its sandboxes, the requests it declines, how a turn reads."""

from collections.abc import Mapping
from enum import StrEnum

from nestor.adapters.executors.common import step
from nestor.adapters.executors.jsonrpc import Message

COMMAND = ("codex", "app-server")

DECLINED: Mapping[str, Message] = {  # every request Codex may send for a person to answer, and its refusal
    "item/commandExecution/requestApproval": {"decision": "decline"},
    "item/fileChange/requestApproval": {"decision": "decline"},
    "execCommandApproval": {"decision": "denied"},
    "applyPatchApproval": {"decision": "denied"},
    "item/tool/requestUserInput": {"answers": {}},
    "mcpServer/elicitation/request": {"action": "decline"},
}

ENDED = ("completed", "failed", "interrupted")


class Sandbox(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "danger-full-access"


def final_answer(turn: Message) -> str:
    """The turn's final answer: its last agent message, the one Codex marks final if any."""
    said = [i for i in turn.get("items") or () if i.get("type") == "agentMessage"]
    final = [i for i in said if i.get("phase") == "final_answer"] or said
    return str(final[-1].get("text") or "") if final else ""


def item_step(item: Message) -> str | None:
    match item.get("type"):
        case "commandExecution":
            return step(f"command: {item.get('command')}")
        case "fileChange":
            return step("editing: " + ", ".join(str(c.get("path")) for c in item.get("changes") or ()))
        case "mcpToolCall":
            return step(f"{item.get('server')}: {item.get('tool')}")
        case "webSearch":
            return step(f"web search: {item.get('query')}")
        case "imageGeneration":
            return "drawing an image"
        case _:
            return None
