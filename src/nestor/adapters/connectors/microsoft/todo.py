"""Microsoft To Do tools: the person's open tasks, adding one, ticking one off, in their default list."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.moments import DAY, day
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.microsoft.graph import GraphApi, Json, in_zone, mailbox_zone
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

MAX_RESULTS = 100

LIST = ToolSpec(
    "todo_list",
    f"List the open tasks of the person's Microsoft To Do: title, notes, due date and id of each. {SHARED}",
    {
        "type": "object",
        "properties": {"max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 50}},
    },
)
ADD = ToolSpec(
    "todo_add",
    "Add a task to the person's Microsoft To Do.",
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
    "todo_complete",
    "Tick off one of the person's Microsoft To Do tasks by id (from todo_list).",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the task id"}},
        "required": ["id"],
    },
)


class TodoTools:
    def __init__(self, account: str, api: Callable[[], GraphApi], known: dict[str, str]) -> None:
        """`known`: what the connector keeps about the account while it runs (where its default list is)."""
        self._account, self._api, self._known = account, api, known

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=LIST, run=self.pending, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=ADD, run=self.add, risk=Risk.WRITE, timeout_s=20.0),
            Tool(spec=COMPLETE, run=self.complete, risk=Risk.WRITE, timeout_s=20.0),
        )

    async def _tasks(self, api: GraphApi) -> str:
        """Where the tasks of the person's default list are."""
        if "tasks" not in self._known:
            lists = await ask("Microsoft To Do", api.get("/me/todo/lists"))
            default = next((f for f in lists.get("value", []) if f.get("wellknownListName") == "defaultList"), None)
            if default is None:
                raise ToolFailed("Microsoft To Do has no default list on this account")
            self._known["tasks"] = f"/me/todo/lists/{segment(str(default['id']))}/tasks"
        return self._known["tasks"]

    async def pending(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        limit = bounded(arguments.get("max_results"), default=50, maximum=MAX_RESULTS)
        api = self._api()
        params = [("$filter", "status ne 'completed'"), ("$top", str(limit))]
        zone = await mailbox_zone(api, self._known)  # a due day is the person's day, not UTC's
        found = await ask("Microsoft To Do", api.get(await self._tasks(api), params, in_zone(zone)))
        tasks = [_task(t) for t in found.get("value", []) if isinstance(t, dict)]
        return {"account": self._account, "tasks": tasks, "note": SHARED}

    async def add(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ToolFailed("give the task a title")
        body: Json = {"title": title}
        if notes := str(arguments.get("notes") or "").strip():
            body["body"] = {"contentType": "text", "content": notes}
        api = self._api()
        zone = await mailbox_zone(api, self._known)  # a due day is the person's day, not UTC's
        if due := str(arguments.get("due") or "").strip():
            body["dueDateTime"] = {"dateTime": f"{day(due).isoformat()}T00:00:00", "timeZone": zone}
        made = await ask("Adding to Microsoft To Do", api.send("POST", await self._tasks(api), body, in_zone(zone)))
        return {"account": self._account, "task": _task(made)}

    async def complete(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task_id = str(arguments.get("id") or "").strip()
        if not task_id:
            raise ToolFailed("give the id of a task listed with todo_list")
        api = self._api()
        zone = await mailbox_zone(api, self._known)
        done = await ask(
            "Ticking off a To Do task",
            api.send("PATCH", f"{await self._tasks(api)}/{segment(task_id)}", {"status": "completed"}, in_zone(zone)),
        )
        return {"account": self._account, "task": _task(done)}


def _task(task: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": task.get("id"),
        "title": task.get("title", ""),
        "notes": (task.get("body") or {}).get("content", ""),
        "due": str((task.get("dueDateTime") or {}).get("dateTime") or "")[:10],
        "done": task.get("status") == "completed",
    }
