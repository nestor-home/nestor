"""Watching and calling through the satellites: the devices the caller may use, a session opened from the browser's
WebRTC offer and ended, a still picture, and who may (`media.access`).

Watching needs `media.view`, calling `media.call`, and the device listing the caller's person (`MediaAccess`) unless
they own the household; setting who may needs `satellites.manage`. A session ends at its longest duration, when the
browser leaves, and when the caller signs out; each is journaled.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.errors import ApiError, not_found
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
from nestor.modules.satellites import MediaAccess, MediaEnd, MediaRefused, MediaSessions, Purpose, Viewer

router = APIRouter(tags=["media"])
Watcher = Annotated[Caller, Depends(allowed(Scope.MEDIA_VIEW, Scope.MEDIA_CALL))]
Manager = Annotated[Caller, Depends(allowed(Scope.SATELLITES_MANAGE))]
SCOPES = {Purpose.VIEW: Scope.MEDIA_VIEW, Purpose.CALL: Scope.MEDIA_CALL}


@router.get("/media/devices")
async def list_media_devices(request: Request, caller: Watcher) -> MediaDevicesOut:
    """The devices the caller may watch or call through, connected or not."""
    nestor = state(request).nestor
    media, viewer = nestor.media, _viewer(caller)
    if media is None:
        return MediaDevicesOut(available=False, devices=[])
    devices = []
    for satellite in nestor.pairing.satellites():
        view = caller.principal.can(Scope.MEDIA_VIEW) and media.may(satellite, viewer, Purpose.VIEW)
        call = caller.principal.can(Scope.MEDIA_CALL) and media.may(satellite, viewer, Purpose.CALL)
        if view or call:
            devices.append(MediaDeviceOut.of(satellite, media.linked(satellite.id), view=view, call=call))
    return MediaDevicesOut(available=True, devices=devices)


@router.post("/satellites/{device_id}/media/sessions")
async def open_media_session(request: Request, caller: Watcher, device_id: str, body: MediaOfferIn) -> MediaSessionOut:
    """Watch or call through the device: the answer to the browser's WebRTC offer."""
    caller.principal.require(SCOPES[body.purpose])
    try:
        opened = await _media(request).open(
            device_id, body.purpose, _viewer(caller), {"sdp": body.sdp, "type": body.type}
        )
    except MediaRefused as refused:
        raise _refusal(refused) from None
    return MediaSessionOut.of(opened)


@router.delete("/media/sessions/{session_id}", status_code=204)
async def close_media_session(request: Request, caller: Watcher, session_id: str) -> Response:
    """End one's own session (an owner: any)."""
    await _media(request).close_session(session_id, MediaEnd.CLOSED, by=_viewer(caller))
    return Response(status_code=204)


@router.post("/satellites/{device_id}/media/snapshot")
async def take_snapshot(request: Request, caller: Watcher, device_id: str) -> Response:
    """A still picture of what the device films now, kept a few days."""
    caller.principal.require(Scope.MEDIA_VIEW)
    nestor = state(request).nestor
    try:
        taken = await _media(request).snapshot(device_id, _viewer(caller))
    except MediaRefused as refused:
        raise _refusal(refused) from None
    return file_response(await nestor.blobs.get(taken.blob.digest), "image/jpeg", taken.name)


@router.put("/satellites/{device_id}/media/access")
async def set_media_access(request: Request, caller: Manager, device_id: str, body: MediaAccessIn) -> MediaAccessOut:
    """Who of the household may watch the device or call through it, and whether its camera may film."""
    admin = state(request)
    people = People(admin.nestor.household)
    if unknown := [p for p in [*body.viewers, *body.callers] if not people.known(p)]:
        raise ApiError(422, "person_unknown", person=unknown[0])
    access = MediaAccess(frozenset(map(PersonId, body.viewers)), frozenset(map(PersonId, body.callers)), body.camera)
    try:
        satellite = await _media(request).set_access(device_id, access, by=caller.person)
    except MediaRefused:
        raise not_found("satellite_unknown") from None
    return MediaAccessOut.of(satellite.access, people)


def _media(request: Request) -> MediaSessions:
    media = state(request).nestor.media
    if media is None:
        raise ApiError(409, "media_off")
    return media


def _viewer(caller: Caller) -> Viewer:
    return Viewer(
        account_id=caller.account_id or "",
        person=caller.person,
        owner=caller.principal.can(Scope.OWNERS_MANAGE),
        signed_in=caller.session.id if caller.session else "",
    )


def _refusal(refused: MediaRefused) -> ApiError:
    if refused.reason == "unknown":
        return not_found("satellite_unknown")
    match refused.reason:
        case "forbidden":
            return ApiError(403, "media_forbidden")
        case "camera_off":
            return ApiError(409, "media_camera_off")
        case "unable":
            return ApiError(409, "media_unable")
        case _:
            return ApiError(409, "media_offline")
