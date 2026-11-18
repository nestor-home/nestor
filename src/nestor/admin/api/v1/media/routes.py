"""Watching and calling through the satellites: the devices the caller may use, a session opened from the browser's
WebRTC offer and ended, a still picture, and who may (`media.access`).

Watching needs `media.view` and the device listing the caller's person (`MediaAccess`), or `media.view.all`; calling
`media.call`, or `media.call.all`. Setting who may needs `satellites.manage`. A session ends at its longest duration,
when the browser leaves, when the caller's admin session ends, and as soon as they may no longer do it; each is
journaled.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.errors import ApiError, ErrorCode, not_found
from nestor.admin.api.v1.media.schemas import (
    MediaAccessIn,
    MediaAccessOut,
    MediaDeviceOut,
    MediaDevicesOut,
    MediaOfferIn,
    MediaSessionOut,
)
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.http import file_response
from nestor.modules.accounts import Scope
from nestor.modules.satellites import MediaAccess, MediaEnd, MediaRefused, MediaSessions, Refusal, Viewer

router = APIRouter(tags=["media"])
Watcher = Annotated[Caller, Depends(allowed(Scope.MEDIA_VIEW, Scope.MEDIA_CALL))]
Manager = Annotated[Caller, Depends(allowed(Scope.SATELLITES_MANAGE))]
REFUSED: dict[Refusal, tuple[int, ErrorCode]] = {
    Refusal.FORBIDDEN: (403, "media_forbidden"),
    Refusal.CAMERA_OFF: (409, "media_camera_off"),
    Refusal.UNABLE: (409, "media_unable"),
    Refusal.OFFLINE: (409, "media_offline"),
}


@router.get("/media/devices")
async def list_media_devices(request: Request, caller: Watcher) -> MediaDevicesOut:
    """The devices the caller may watch or call through, connected or not."""
    media = state(request).nestor.media
    if media is None:
        return MediaDevicesOut(available=False, devices=[])
    return MediaDevicesOut(
        available=True, devices=[MediaDeviceOut.of(o) for o in media.offers(_viewer(request, caller))]
    )


@router.post("/satellites/{device_id}/media/sessions")
async def open_media_session(request: Request, caller: Watcher, device_id: str, body: MediaOfferIn) -> MediaSessionOut:
    """Watch or call through the device: the answer to the browser's WebRTC offer."""
    try:
        live = await _media(request).open(
            device_id, body.purpose, _viewer(request, caller), {"sdp": body.sdp, "type": body.type}
        )
    except MediaRefused as refused:
        raise _refusal(refused) from None
    return MediaSessionOut.of(live)


@router.delete("/media/sessions/{session_id}", status_code=204)
async def close_media_session(request: Request, caller: Watcher, session_id: str) -> Response:
    """End one's own session (or any, for whom may on every device)."""
    await _media(request).close_session(session_id, MediaEnd.CLOSED, by=_viewer(request, caller))
    return Response(status_code=204)


@router.post("/satellites/{device_id}/media/snapshot")
async def take_snapshot(request: Request, caller: Watcher, device_id: str) -> Response:
    """A still picture of what the device films now, kept a few days."""
    try:
        taken, jpeg = await _media(request).snapshot(device_id, _viewer(request, caller))
    except MediaRefused as refused:
        raise _refusal(refused) from None
    return file_response(jpeg, "image/jpeg", taken.name)


@router.put("/satellites/{device_id}/media/access")
async def set_media_access(request: Request, caller: Manager, device_id: str, body: MediaAccessIn) -> MediaAccessOut:
    """Who of the household may watch the device or call through it, and whether its camera may film; what it no
    longer allows ends at once."""
    admin = state(request)
    people = People(admin.nestor.household)
    named = [*body.viewers, *body.callers, *body.privacy.home_people]
    if unknown := [p for p in named if not people.known(p)]:
        raise ApiError(422, "person_unknown", person=unknown[0])
    if body.privacy.off_when_home and admin.nestor.presence is None:
        raise ApiError(409, "privacy_needs_presence")
    access = MediaAccess(
        frozenset(map(PersonId, body.viewers)),
        frozenset(map(PersonId, body.callers)),
        body.camera,
        body.privacy.to_domain(),
    )
    try:
        satellite = await admin.nestor.pairing.set_access(device_id, access, by=caller.person)
    except KeyError:
        raise not_found("satellite_unknown") from None
    if admin.nestor.media is not None:
        await admin.nestor.media.check()
    return MediaAccessOut.of(satellite.access, people)


def _media(request: Request) -> MediaSessions:
    media = state(request).nestor.media
    if media is None:
        raise ApiError(409, "media_off")
    return media


def _viewer(request: Request, caller: Caller) -> Viewer:
    """The caller, as long as their admin session lasts: their role is read again at each check."""
    admin, session = state(request), caller.session

    def now() -> Viewer | None:
        account = admin.accounts.accounts.get(session.account_id) if session else None
        if session is None or account is None or account.disabled or not admin.sessions.alive(session):
            return None
        return Viewer.of(account.principal())

    return Viewer.of(caller.principal, now)


def _refusal(refused: MediaRefused) -> ApiError:
    if refused.reason is Refusal.UNKNOWN:
        return not_found("satellite_unknown")
    status, code = REFUSED[refused.reason]
    return ApiError(status, code, off=refused.off or "")
