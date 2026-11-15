"""What every task-list connector shares: its three tools as the model sees them, and a task as it reads one."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from nestor.adapters.connectors.common.moments import DAY
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import ToolFailed

MAX_TASKS = 100


def task_specs(prefix: str, tasks: str, shared: str) -> tuple[ToolSpec, ToolSpec, ToolSpec]:
    """`<prefix>_list`, `<prefix>_add` and `<prefix>_complete` for `tasks` ("the person's Google Tasks")."""
    listed = ToolSpec(
        f"{prefix}_list",
        f"List the open tasks of {tasks}: title, notes, due date and id of each. {shared}",
        {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "minimum": 1, "maximum": MAX_TASKS, "default": 50}},
        },
    )
    add = ToolSpec(
        f"{prefix}_add",
        f"Add a task to {tasks}.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "due": {"type": "string", "description": DAY},
            },
            "required": ["title"],
        },
    )
    complete = ToolSpec(
        f"{prefix}_complete",
        f"Tick off one of the tasks of {tasks} by id (from {prefix}_list).",
        {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "the task id"}},
            "required": ["id"],
        },
    )
    return listed, add, complete


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    id: str | None
    title: str
    notes: str = ""
    due: str = ""  # the day, YYYY-MM-DD
    done: bool = False

    def shown(self) -> dict[str, object]:
        return asdict(self)


def title(arguments: Mapping[str, object]) -> str:
    found = str(arguments.get("title") or "").strip()
    if not found:
        raise ToolFailed("give the task a title")
    return found


def task_id_of(arguments: Mapping[str, object], prefix: str) -> str:
    found = str(arguments.get("id") or "").strip()
    if not found:
        raise ToolFailed(f"give the id of a task listed with {prefix}_list")
    return found
