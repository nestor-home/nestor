"""Alerts: what the agent does later, regularly, or when something happens, for whom, why each rang, and cancelling
one.

`alerts.manage.all` reaches every alert; `alerts.manage.own` those set for the account's person.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.access import reachable_alert, reaches_alert
from nestor.admin.api.v1.alerts.schemas import AlertOut, AlertsOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.initiative import AlertEnd

router = APIRouter(tags=["alerts"])
Manager = Annotated[Caller, Depends(allowed(Scope.ALERTS_MANAGE_ALL, Scope.ALERTS_MANAGE_OWN))]


@router.get("/alerts")
async def list_alerts(request: Request, caller: Manager) -> AlertsOut:
    nestor = state(request).nestor
    book, people = nestor.alert_book, People(nestor.household)
    return AlertsOut(
        alerts=[AlertOut.of(a, book, people) for a in book.upcoming() if reaches_alert(caller, a)],
        kinds=sorted(book.kinds),
    )


@router.get("/alerts/{alert_id}")
async def get_alert(request: Request, caller: Manager, alert_id: str) -> AlertOut:
    """One active alert; 404 when unknown, ended or out of reach."""
    admin = state(request)
    alert = reachable_alert(admin, caller, alert_id)
    return AlertOut.of(alert, admin.nestor.alert_book, People(admin.nestor.household))


@router.post("/alerts/{alert_id}/cancel", status_code=204)
async def cancel_alert(request: Request, caller: Manager, alert_id: str) -> Response:
    admin = state(request)
    alert = reachable_alert(admin, caller, alert_id)
    await admin.nestor.alert_book.end(alert.id, AlertEnd.CANCELLED, by=caller.person)
    return Response(status_code=204)
