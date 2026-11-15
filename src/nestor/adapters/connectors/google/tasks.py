"""Google Tasks tools: the person's open tasks, adding one, ticking one off."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.moments import day
from nestor.adapters.connectors.common.tasks import MAX_TASKS, NO_TITLE, Task, task_specs
from nestor.adapters.connectors.common.tools import ask, required
from nestor.adapters.connectors.google.api import GoogleApi, Json
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, bounded

TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"

LIST, ADD, COMPLETE = task_specs("google_tasks", "the person's Google Tasks", SHARED)


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
        limit = bounded(arguments.get("max_results"), default=50, maximum=MAX_TASKS)
        params = [("showCompleted", "false"), ("maxResults", str(limit))]
        found = await ask("Google Tasks", self._api().get(TASKS_URL, params))
        tasks = [_task(t).shown() for t in found.get("items", []) if isinstance(t, dict)]
        return {"account": self._account, "tasks": tasks, "note": SHARED}

    async def add(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        body: Json = {"title": required(arguments, "title", NO_TITLE)}
        if notes := str(arguments.get("notes") or "").strip():
            body["notes"] = notes
        if due := str(arguments.get("due") or "").strip():
            body["due"] = f"{day(due).isoformat()}T00:00:00.000Z"  # Google keeps only the day, as its midnight in UTC
        made = await ask("Adding to Google Tasks", self._api().send("POST", TASKS_URL, body))
        return {"account": self._account, "task": _task(made).shown()}

    async def complete(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        task_id = required(arguments, "id", "give the id of a task listed with google_tasks_list")
        done = await ask(
            "Ticking off a Google task",
            self._api().send("PATCH", f"{TASKS_URL}/{segment(task_id)}", {"status": "completed"}),
        )
        return {"account": self._account, "task": _task(done).shown()}


def _task(task: Mapping[str, Any]) -> Task:
    return Task(
        id=task.get("id"),
        title=str(task.get("title", "")),
        notes=str(task.get("notes", "")),
        due=str(task.get("due") or "")[:10],
        done=task.get("status") == "completed",
    )
