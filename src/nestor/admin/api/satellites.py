"""Pairing satellites from the command line: approve a code, revoke a device."""

import json

from fastapi import APIRouter, Request

from nestor.admin.api.guard import ApiRefused, Authorized
from nestor.admin.state import state
from nestor.core import Capability, ContractError
from nestor.modules.satellites import PairingRefused, Satellite

router = APIRouter(prefix="/api/satellites")


@router.post("/approve")
async def approve(request: Request, _: Authorized) -> dict[str, object]:
    """Body: `{"code": "123456", "capabilities": ["audio.capture", …]}`; all it declared when absent."""
    code, granted = _approval(await request.body())
    try:
        satellite = await state(request).nestor.pairing.approve(code, capabilities=granted)
    except PairingRefused as refused:
        raise ApiRefused(400, str(refused)) from None
    return _described(satellite)


@router.post("/{device_id}/revoke")
async def revoke(request: Request, device_id: str, _: Authorized) -> dict[str, object]:
    try:
        await state(request).nestor.pairing.revoke(device_id)
    except ContractError as unknown:
        raise ApiRefused(404, str(unknown)) from None
    return {"revoked": device_id}


def _approval(body: bytes) -> tuple[str, list[Capability] | None]:
    try:
        data = json.loads(body)
    except ValueError:
        raise ApiRefused(400, "the body must be JSON") from None
    if not isinstance(data, dict) or set(data) - {"code", "capabilities"} or not isinstance(data.get("code"), str):
        raise ApiRefused(400, 'expected {"code": "…", "capabilities": [...]}')
    capabilities = data.get("capabilities")
    if capabilities is None:
        return data["code"].strip(), None
    if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
        raise ApiRefused(400, "capabilities must be a list of names")
    return data["code"].strip(), [Capability(c) for c in capabilities]


def _described(satellite: Satellite) -> dict[str, object]:
    return {
        "device": satellite.id,
        "model": satellite.model,
        "room": satellite.room,
        "capabilities": sorted(satellite.capabilities),
    }
