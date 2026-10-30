"""What the central agent sees of delegation: three tools and a section of its instructions."""

from collections.abc import Mapping, Sequence

from nestor.core import ContractError
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.delegation.types import Notify, TaskStatus
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.conversation import ContextProvider
from nestor.modules.household import Person

HOW_TO_DELEGATE = """You never do long work yourself: you talk, and you hand over to an executor anything that needs \
acting, searching or computing beyond your own tools. To hand over, call delegate_task with a precise, verifiable \
objective, then say in a very short sentence that it is started. The task runs in the background: keep talking \
meanwhile; its result will be announced when it arrives. If the person wants the result in writing (they are leaving, \
"write me when it's done"), set notify to "message". When asked how it is going, call task_status. To abandon a task, \
call cancel_task, and only say it stopped if the stop is confirmed."""

NO_EXECUTOR = """No executor is plugged in: you cannot carry out long tasks, search or act beyond your own tools. \
If asked, say so simply."""


class Delegation(ToolProvider, ContextProvider):
    name = "delegation"

    def __init__(self, tasks: TaskManager) -> None:
        self.tasks = tasks

    def tools(self) -> Sequence[Tool]:
        if not self.tasks.executors:
            return ()
        names = list(self.tasks.executors)
        delegate_parameters: dict[str, object] = {
            "objective": {"type": "string", "description": "Precise, verifiable objective"},
            "notify": {
                "type": "string",
                "enum": [n.value for n in Notify],
                "description": "auto: announce it in this conversation if possible; message: send it in writing",
            },
        }
        if len(names) > 1:
            delegate_parameters["executor"] = {"type": "string", "enum": names}
        return (
            Tool(
                spec=ToolSpec(
                    "delegate_task",
                    "Hand a long task over to an executor; it runs in the background.",
                    {"type": "object", "properties": delegate_parameters, "required": ["objective"]},
                ),
                run=self._delegate,
                risk=Risk.WRITE,
            ),
            Tool(spec=ToolSpec("task_status", "Status and latest progress of delegated tasks."), run=self._status),
            Tool(
                spec=ToolSpec(
                    "cancel_task",
                    "Stop a delegated task the person wants to abandon; reports whether the stop is confirmed. "
                    "Effects already produced remain.",
                    {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
                ),
                run=self._cancel,
                risk=Risk.WRITE,
                timeout_s=30.0,
            ),
        )

    async def context(self, person: Person | None, address: Address) -> str | None:
        if not self.tasks.executors:
            return NO_EXECUTOR
        executors = "\n".join(f"- {e.name}: {e.description}" for e in self.tasks.executors.values())
        lines = [
            HOW_TO_DELEGATE,
            f"Your executors and what they can really do:\n{executors}\n"
            "Nothing else: for any other request, say right away that you cannot, without starting a task.",
        ]
        if running := self.tasks.running():
            listed = "\n".join(f"- {t.id}: {t.objective}" for t in running)
            lines.append(f"Tasks running now:\n{listed}")
        return "\n\n".join(lines)

    async def _delegate(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        try:
            notify = Notify(str(arguments.get("notify", Notify.AUTO)))
        except ValueError:
            raise ToolFailed(f"notify must be one of: {', '.join(Notify)}") from None
        executor = arguments.get("executor")
        try:
            task = await self.tasks.delegate(
                str(arguments["objective"]),
                origin=context.address,
                requested_by=context.person,
                notify=notify,
                executor=str(executor) if executor else None,
                exchange=context.exchange,
            )
        except ContractError as error:
            raise ToolFailed(str(error)) from None
        return {"task_id": task.id, "status": "running", "note": "Started: tell the person in a few words."}

    async def _status(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        """Running tasks, and the last finished ones without their result (already announced), so the
        context does not grow with the history."""
        return {
            "running": [t.snapshot() for t in self.tasks.running()],
            "recently_finished": [t.snapshot() for t in self.tasks.recent()],
        }

    async def _cancel(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        outcome = await self.tasks.cancel(str(arguments["task_id"]))
        confirmed = outcome.status is TaskStatus.CANCELLED
        return {
            "stopped": confirmed,
            "status": outcome.status.value,
            **({"error": outcome.error} if outcome.error else {}),
        }
