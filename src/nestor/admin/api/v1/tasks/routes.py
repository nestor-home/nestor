"""Delegated tasks: the running ones (which can be stopped) and the latest that ended.

`tasks.manage` reaches every task; `tasks.manage.own` the tasks the account's person asked for.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import reachable_task, reaches_task
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.api.v1.tasks.afterwards import Afterwards
from nestor.admin.api.v1.tasks.schemas import CancelOut, TaskOut, TasksOut
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.cognition import TaskStatus

router = APIRouter(tags=["tasks"])
Manager = Annotated[Caller, Depends(allowed(Scope.TASKS_MANAGE, Scope.TASKS_MANAGE_OWN))]
RECENT = 20


@router.get("/tasks")
async def list_tasks(request: Request, caller: Manager) -> TasksOut:
    admin = state(request)
    people, afterwards, manager = People(admin.nestor.household), await Afterwards.of(admin), admin.nestor.tasks
    return TasksOut(
        running=[TaskOut.of(t, people, afterwards) for t in manager.running() if reaches_task(caller, t)],
        recent=[TaskOut.of(t, people, afterwards) for t in reversed(manager.recent(RECENT)) if reaches_task(caller, t)],
    )


@router.get("/tasks/{task_id}")
async def get_task(request: Request, caller: Manager, task_id: str) -> TaskOut:
    """One task, running or among those the manager still keeps; 404 when unknown or out of reach."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    return TaskOut.of(task, People(admin.nestor.household), await Afterwards.of(admin))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, caller: Manager, task_id: str) -> CancelOut:
    """Ask the executor to stop; 404 when the task is unknown, out of reach or already ended."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id, running=True)
    outcome = await admin.nestor.tasks.cancel(task_id)
    return CancelOut(
        task=TaskOut.of(task, People(admin.nestor.household), await Afterwards.of(admin)),
        confirmed=outcome.status is TaskStatus.CANCELLED,
    )
