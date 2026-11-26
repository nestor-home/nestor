"""Delegated tasks: each a thread with its executor, which the admin lists, opens, directs (an answer to its question,
a new instruction, steering while it works), stops, renames and archives.

`tasks.manage` reaches every task; `tasks.manage.own` the tasks of the account's person. An instruction is given in
the name of the account's person.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from nestor.admin.api.v1.access import reachable_task, reaches_task
from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.api.v1.tasks.schemas import (
    DirectedOut,
    InstructionIn,
    StopOut,
    TaskChangedOut,
    TaskEditIn,
    TaskOut,
    TasksOut,
    TaskThreadOut,
)
from nestor.admin.state import AdminState, state
from nestor.core import ContractError
from nestor.http import file_response
from nestor.modules.accounts import Scope
from nestor.modules.cognition import TurnStatus
from nestor.modules.cognition.delegation import Directed, ExecutorUnavailable, Task

router = APIRouter(tags=["tasks"])
Manager = Annotated[Caller, Depends(allowed(Scope.TASKS_MANAGE, Scope.TASKS_MANAGE_OWN))]


@router.get("/tasks")
async def list_tasks(request: Request, caller: Manager, archived: bool = False) -> TasksOut:
    """The tasks the caller reaches that are not archived: waiting on someone first, then working, then the latest
    active; with `archived`, the archived ones only, the latest first."""
    nestor = state(request).nestor
    people, tasks = People(nestor.household), nestor.tasks
    found = [t for t in tasks.of(archived=archived) if reaches_task(caller, t)]
    return TasksOut(tasks=[TaskOut.of(t, people, tasks.executors.get(t.executor)) for t in found])


@router.get("/tasks/{task_id}")
async def get_task(request: Request, caller: Manager, task_id: str) -> TaskThreadOut:
    """One task with its thread; 404 when unknown or out of reach."""
    admin = state(request)
    return _thread(admin, reachable_task(admin, caller, task_id))


@router.post("/tasks/{task_id}/instructions")
async def direct_task(request: Request, caller: Manager, task_id: str, body: InstructionIn) -> DirectedOut:
    """Give a task an instruction in the name of the account's person: taken into the turn that works when its
    executor can, else it opens the next turn, in the same thread (the answer to its question). 409 when the turn that
    works could not be stopped for it, or when the task's executor is no longer plugged in: nothing was given."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    if caller.person is None:
        raise ApiError(403, "person_required")
    try:
        directed = await admin.nestor.tasks.direct(task.id, body.text, by=caller.person, asked=True)
    except ExecutorUnavailable:
        raise ApiError(409, "executor_unavailable") from None
    except ContractError:
        raise not_found("task_unknown") from None
    if directed is Directed.BUSY:
        raise ApiError(409, "task_not_stopped")
    return DirectedOut(task=_thread(admin, task), steered=directed is Directed.STEERED)


@router.post("/tasks/{task_id}/stop")
async def stop_task(request: Request, caller: Manager, task_id: str) -> StopOut:
    """Stop the turn that works; the task stays. 404 when the task is unknown or out of reach."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    outcome = await admin.nestor.tasks.stop(task.id, by=caller.person)
    return StopOut(task=_thread(admin, task), confirmed=outcome.status is TurnStatus.STOPPED)


@router.patch("/tasks/{task_id}")
async def rename_task(request: Request, caller: Manager, task_id: str, body: TaskEditIn) -> TaskChangedOut:
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    try:
        await admin.nestor.tasks.rename(task.id, body.title, by=caller.person)
    except ContractError:
        raise ApiError(422, "invalid") from None
    return TaskChangedOut(task=_thread(admin, task))


@router.post("/tasks/{task_id}/archive")
async def archive_task(request: Request, caller: Manager, task_id: str) -> TaskChangedOut:
    """Put a task away, its working turn stopped first; an instruction opens it again."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    await admin.nestor.tasks.archive(task.id, by=caller.person)
    return TaskChangedOut(task=_thread(admin, task))


@router.get(
    "/tasks/{task_id}/turns/{turn_id}/files/{index}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "The file, as it was sent or made"}},
)
async def get_task_file(request: Request, caller: Manager, task_id: str, turn_id: str, index: int) -> Response:
    """A file of a turn (`TurnOut.files`); 404 when the task is out of reach or has no such file."""
    admin = state(request)
    task = reachable_task(admin, caller, task_id)
    turn = task.turn_of(turn_id)
    files = (*turn.given, *turn.files) if turn else ()
    if not 0 <= index < len(files):
        raise not_found("attachment_unknown")
    file = files[index]
    try:
        data = await admin.nestor.blobs.get(file.blob.digest)
    except KeyError:
        raise not_found("attachment_unknown") from None
    return file_response(data, file.blob.media_type, file.name)


def _thread(admin: AdminState, task: Task) -> TaskThreadOut:
    nestor = admin.nestor
    executor = nestor.tasks.executors.get(task.executor)
    return TaskThreadOut.full(task, People(nestor.household), executor, nestor.spoken_channels())
