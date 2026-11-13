"""Google Tasks tools: the person's open tasks, adding one, ticking one off."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.moments import DAY, day
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.google.api import GoogleApi, Json
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"
MAX_RESULTS = 100

LIST = ToolSpec(
    "google_tasks_list",
    f"List the open tasks of the person's Google Tasks: title, notes, due date and id of each. {SHARED}",
    {
        "type": "object",
        "properties": {"max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 50}},
    },
)
ADD = ToolSpec(
    "google_tasks_add",
    "Add a task to the person's Google Tasks.",
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
COMPLETE = ToolSpec(
    "google_tasks_complete",
    "Tick off one of the person's Google Tasks by id (from google_tasks_list).",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the task id"}},
        "required": ["id"],
    },
)


class TaskTools:
    def __init__(self, account: str, api: Callable[[], GoogleApi]) -> None:
        self._account, self._api = account, api

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=LIST, run=self.pending, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=ADD, run=self.add, risk=Risk.WRITE, timeout_s=20.0),
            Tool(spec=COMPLETE, run=self.complete, risk=Risk.WRITE, timeout_s=20.0),
        )

    async def pending(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        limit = bounded(arguments.get("max_results"), default=50, maximum=MAX_RESULTS)
        params = [("showCompleted", "false"), ("maxResults", str(limit))]
        found = await ask("Google Tasks", self._api().get(TASKS_URL, params))
        tasks = [_task(t) for t in found.get("items", []) if isinstance(t, dict)]
        return {"account": self._account, "tasks": tasks, "note": SHARED}

    async def add(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ToolFailed("give the task a title")
        body: Json = {"title": title}
        if notes := str(arguments.get("notes") or "").strip():
            body["notes"] = notes
        if due := str(arguments.get("due") or "").strip():
            body["due"] = f"{day(due).isoformat()}T00:00:00.000Z"  # Google keeps only the day, as its midnight in UTC
        made = await ask("Adding to Google Tasks", self._api().send("POST", TASKS_URL, body))
        return {"account": self._account, "task": _task(made)}

    async def complete(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task_id = str(arguments.get("id") or "").strip()
        if not task_id:
            raise ToolFailed("give the id of a task listed with google_tasks_list")
        done = await ask(
            "Ticking off a Google task",
            self._api().send("PATCH", f"{TASKS_URL}/{segment(task_id)}", {"status": "completed"}),
        )
        return {"account": self._account, "task": _task(done)}


def _task(task: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": task.get("id"),
        "title": task.get("title", ""),
        "notes": task.get("notes", ""),
        "due": str(task.get("due") or "")[:10],
        "done": task.get("status") == "completed",
    }
