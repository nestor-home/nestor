"""Delegated tasks: the ones running (they can be stopped) and the latest ones that ended."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.errors import Refused
from nestor.admin.guard import Checked, LoggedIn
from nestor.admin.presentation import french_task_status
from nestor.admin.state import state
from nestor.modules.cognition import TaskStatus

router = APIRouter()

RECENT = 20


@router.get("/tasks")
async def tasks_page(request: Request, session: LoggedIn) -> HTMLResponse:
    admin = state(request)
    manager = admin.nestor.tasks
    names = {p.id: p.name for p in admin.nestor.household.people}
    return admin.pages.render(
        request,
        "tasks.html",
        session,
        running=manager.running(),
        recent=list(reversed(manager.recent(RECENT))),
        names=names,
        label=french_task_status,
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(request: Request, session: Checked, task_id: str) -> Response:
    manager = state(request).nestor.tasks
    task = manager.tasks.get(task_id)
    if task is None or task.status is not TaskStatus.RUNNING:
        raise Refused(404, "Tâche introuvable", "Cette tâche n'existe pas ou est déjà terminée.", back="/tasks")
    outcome = await manager.cancel(task_id)
    if outcome.status is TaskStatus.CANCELLED:
        session.notify(f"Tâche {task_id} arrêtée.")
    else:
        session.notify(f"Arrêt de la tâche {task_id} demandé, sans confirmation de l'exécutant : {outcome.error}.")
    return RedirectResponse("/tasks", status_code=303)
