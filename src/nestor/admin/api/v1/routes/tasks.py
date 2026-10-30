"""Delegated tasks: the running ones (which can be stopped) and the latest that ended.

`tasks.manage` reaches every task; `tasks.manage.own` the tasks the account's person asked for.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.models import People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import Phrasebook, subject
from nestor.admin.state import AdminState, state
from nestor.modules.accounts import Scope
from nestor.modules.channels import Address, Medium
from nestor.modules.cognition import TaskStatus
from nestor.modules.cognition.delegation.events import TaskDelivered
from nestor.modules.cognition.delegation.service import Task
from nestor.modules.initiative import Delivered

router = APIRouter(tags=["tasks"])
Manager = Annotated[Caller, Depends(allowed(Scope.TASKS_MANAGE, Scope.TASKS_MANAGE_OWN))]
RECENT = 20


class OriginOut(BaseModel):
    session: str  # the conversation it was asked in
    channel: str


class DeliveredOut(BaseModel):
    at: datetime
    channel: str
    room: str | None  # when it was said aloud


class TaskOut(BaseModel):
    id: str
    objective: str
    executor: str
    status: TaskStatus
    status_label: str
    requested_by: PersonRef | None
    origin: OriginOut
    delivered: DeliveredOut | None  # where and when its result reached the person
    started_at: datetime
    steps: list[str]  # the latest progress reports
    result: str | None
    error: str | None


class TasksOut(BaseModel):
    running: list[TaskOut]
    recent: list[TaskOut]  # ended, newest first


class CancelOut(BaseModel):
    task: TaskOut
    confirmed: bool  # False: the executor did not confirm the stop (see `task.error`)


def _reaches(caller: Caller, task: Task) -> bool:
    return caller.principal.reaches(task.requested_by, every=Scope.TASKS_MANAGE, own=Scope.TASKS_MANAGE_OWN)


async def deliveries(admin: AdminState) -> dict[str, DeliveredOut]:
    """Where each task's result was passed on: in the conversation, or by the courier (the latest wins)."""
    spoken = {c.channel_id for c in admin.nestor.channels if c.medium is Medium.SPOKEN}
    found: dict[str, DeliveredOut] = {}

    def out(at: datetime, address: Address) -> DeliveredOut:
        room = address.conversation if address.channel in spoken else None
        return DeliveredOut(at=at, channel=address.channel, room=room)

    for event in await admin.nestor.journal.history(TaskDelivered, Delivered):
        if isinstance(event, TaskDelivered):
            found[event.task_id] = out(event.at, event.address)
        elif (about := subject(event.about))["subject"] == "task":
            found[about["id"]] = out(event.at, event.address)
    return found


def _task(task: Task, people: People, words: Phrasebook, delivered: dict[str, DeliveredOut]) -> TaskOut:
    outcome = task.outcome
    return TaskOut(
        id=task.id,
        objective=task.objective,
        executor=task.executor,
        status=task.status,
        status_label=words.task_status(task.status),
        requested_by=people.ref(task.requested_by),
        origin=OriginOut(session=str(task.origin), channel=task.origin.channel),
        delivered=delivered.get(task.id),
        started_at=task.started_at,
        steps=task.steps[-5:],
        result=outcome.result if outcome else None,
        error=outcome.error if outcome else None,
    )


@router.get("/tasks")
async def list_tasks(request: Request, caller: Manager) -> TasksOut:
    nestor = state(request).nestor
    people = People(nestor.household)
    manager = nestor.tasks
    delivered = await deliveries(state(request))
    return TasksOut(
        running=[_task(t, people, caller.phrasebook, delivered) for t in manager.running() if _reaches(caller, t)],
        recent=[
            _task(t, people, caller.phrasebook, delivered)
            for t in reversed(manager.recent(RECENT))
            if _reaches(caller, t)
        ],
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, caller: Manager, task_id: str) -> CancelOut:
    """Ask the executor to stop; 404 when the task is unknown, out of reach or already ended."""
    nestor = state(request).nestor
    task = nestor.tasks.tasks.get(task_id)
    if task is None or task.status is not TaskStatus.RUNNING or not _reaches(caller, task):
        raise not_found("task_unknown")
    outcome = await nestor.tasks.cancel(task_id)
    return CancelOut(
        task=_task(task, People(nestor.household), caller.phrasebook, {}),
        confirmed=outcome.status is TaskStatus.CANCELLED,
    )
