"""Codex's app-server as Nestor speaks to it: its command, its sandboxes, the requests it declines, how a turn reads."""

from collections.abc import Mapping
from enum import StrEnum

from nestor.adapters.executors.jsonrpc import Message, RpcError

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
UNKNOWN_THREAD = "no rollout found for thread id"  # how `thread/resume` refuses a thread it has no record of (0.160)


def unknown_thread(error: RpcError) -> bool:
    """Whether Codex refused to resume a thread because it no longer has it (its records deleted, another home)."""
    return error.message.startswith(UNKNOWN_THREAD)


class Sandbox(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "danger-full-access"


def final_answer(turn: Message) -> str:
    """The turn's final answer: its last agent message, the one Codex marks final if any."""
    said = [i for i in turn.get("items") or () if i.get("type") == "agentMessage"]
    final = [i for i in said if i.get("phase") == "final_answer"] or said
    return str(final[-1].get("text") or "") if final else ""


def item_step(method: str, item: Message) -> str | None:
    """What an item of the turn says the agent does, as one step of its progress: its own commentary and plan once
    written (`item/completed`), the files it edits, the tools it calls, its searches as it starts them
    (`item/started`). A command it runs is said without its command line: the household reads the steps, and a
    command may carry a secret."""
    match method, item.get("type"):
        case "item/completed", "agentMessage" if item.get("phase") == "commentary" and item.get("text"):
            return str(item["text"])
        case "item/completed", "plan" if item.get("text"):
            return str(item["text"])
        case "item/started", "commandExecution":
            return "running a command"
        case "item/started", "fileChange":
            return "editing: " + ", ".join(str(c.get("path")) for c in item.get("changes") or ())
        case "item/started", "mcpToolCall":
            return f"{item.get('server')}: {item.get('tool')}"
        case "item/started", "webSearch":
            return f"web search: {item.get('query')}"
        case "item/started", "imageGeneration":
            return "drawing an image"
        case _:
            return None
