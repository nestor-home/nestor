"""Satellites: devices waiting to be paired, and the paired ones with what they may do.

Approving needs the code the device shows: it proves the person approving can see the device. The
code is never displayed here. What a satellite may do can be narrowed at approval.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from nestor.admin.auth import Session
from nestor.admin.pages.errors import Refused
from nestor.admin.pages.guard import Checked, LoggedIn
from nestor.admin.pages.rendering import pages_of
from nestor.admin.state import AdminState, state
from nestor.core import Capability, ContractError, PersonId, utc_now
from nestor.modules.channels import Medium
from nestor.modules.satellites import PairingRefused, SatellitePaired

router = APIRouter()

CODE = re.compile(r"^\d{6}$")


@router.get("/satellites")
async def satellites_page(request: Request, session: LoggedIn) -> HTMLResponse:
    return await _page(request, session)


@router.post("/satellites/approve")
async def approve(request: Request, session: Checked) -> Response:
    admin = state(request)
    form = await request.form()
    code = re.sub(r"\s", "", str(form.get("code", "")))
    by = str(form.get("by", ""))
    if by and by not in {p.id for p in admin.nestor.household.people}:
        raise Refused(400, "Personne inconnue", "Choisissez une personne du foyer.", back="/satellites")
    granted = [Capability(str(c)) for c in form.getlist("capability")]
    if not CODE.match(code):
        return await _page(request, session, status=400, error="Le code est fait de 6 chiffres, lus sur l'appareil.")
    try:
        satellite = await admin.nestor.pairing.approve(
            code,
            by=PersonId(by) if by else None,
            capabilities=granted,
            pairing_id=str(form.get("pairing", "")) or None,  # the code must be the one shown by this device
        )
    except PairingRefused:
        return await _page(
            request, session, status=400, error="Aucun appareil n'attend ce code : il est faux ou a expiré."
        )
    session.notify(f"Satellite {satellite.id} (pièce « {satellite.room} ») appairé.")
    return RedirectResponse("/satellites", status_code=303)


@router.post("/satellites/{device_id}/revoke")
async def revoke(request: Request, session: Checked, device_id: str, confirm: Annotated[str, Form()] = "") -> Response:
    if confirm != "yes":
        raise Refused(
            400, "Confirmation manquante", "Cochez la case de confirmation pour révoquer.", back="/satellites"
        )
    try:
        await state(request).nestor.pairing.revoke(device_id)
    except ContractError:
        raise Refused(404, "Satellite inconnu", "Ce satellite n'est pas ou plus appairé.", back="/satellites") from None
    session.notify(f"Satellite {device_id} révoqué : il ne peut plus se connecter.")
    return RedirectResponse("/satellites", status_code=303)


async def _page(request: Request, session: Session, *, status: int = 200, error: str = "") -> HTMLResponse:
    admin = state(request)
    pairing = admin.nestor.pairing
    approvals = {e.device.id: e for e in await admin.nestor.journal.history(SatellitePaired)}  # the latest wins
    now = utc_now()
    return pages_of(request).render(
        request,
        "satellites.html",
        session,
        status=status,
        error=error,
        pending=[(p, max(0, int((p.expires_at - now).total_seconds()))) for p in pairing.pending()],
        satellites=pairing.satellites(),
        approvals=approvals,
        live=_live_rooms(admin),
        people=admin.nestor.household.people,
        names={p.id: p.name for p in admin.nestor.household.people},
        label=pages_of(request).phrasebook.capability,
    )


def _live_rooms(admin: AdminState) -> frozenset[str] | None:
    """Rooms a spoken channel can be heard in right now (the voice channel's live sessions); `None`
    without any spoken channel, when nobody can tell."""
    spoken = [c.rooms for c in admin.nestor.channels if c.medium is Medium.SPOKEN]
    return frozenset().union(*spoken) if spoken else None
