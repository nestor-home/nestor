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
from nestor.admin.presentation import french_task_status
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.cognition import TaskStatus
from nestor.modules.cognition.delegation.service import Task

router = APIRouter(tags=["tasks"])
Manager = Annotated[Caller, Depends(allowed(Scope.TASKS_MANAGE, Scope.TASKS_MANAGE_OWN))]
RECENT = 20


class TaskOut(BaseModel):
    id: str
    objective: str
    executor: str
    status: TaskStatus
    status_label: str
    requested_by: PersonRef | None
    origin: str  # the conversation it was asked in
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


def _task(task: Task, people: People) -> TaskOut:
    outcome = task.outcome
    return TaskOut(
        id=task.id,
        objective=task.objective,
        executor=task.executor,
        status=task.status,
        status_label=french_task_status(task.status),
        requested_by=people.ref(task.requested_by),
        origin=str(task.origin),
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
    return TasksOut(
        running=[_task(t, people) for t in manager.running() if _reaches(caller, t)],
        recent=[_task(t, people) for t in reversed(manager.recent(RECENT)) if _reaches(caller, t)],
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, caller: Manager, task_id: str) -> CancelOut:
    """Ask the executor to stop; 404 when the task is unknown, out of reach or already ended."""
    nestor = state(request).nestor
    task = nestor.tasks.tasks.get(task_id)
    if task is None or task.status is not TaskStatus.RUNNING or not _reaches(caller, task):
        raise not_found("Cette tâche n'existe pas ou est déjà terminée.")
    outcome = await nestor.tasks.cancel(task_id)
    return CancelOut(task=_task(task, People(nestor.household)), confirmed=outcome.status is TaskStatus.CANCELLED)
