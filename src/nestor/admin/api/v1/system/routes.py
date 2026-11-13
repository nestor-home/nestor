"""What is plugged in: every configured adapter and paired satellite, its brand, version and health."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor import __version__
from nestor.admin.api.v1.agent.schemas import AgentOut
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.system.schemas import (
    ComponentOut,
    InstallIn,
    NestorOut,
    RestartIn,
    RestartOut,
    SystemOut,
    UpdatesOut,
)
from nestor.admin.state import state
from nestor.core import ContractError
from nestor.modules.accounts import Scope

router = APIRouter(tags=["system"])
Reader = Annotated[Caller, Depends(allowed(Scope.SYSTEM_READ))]
Restarter = Annotated[Caller, Depends(allowed(Scope.CONFIG_MANAGE, local=True))]


@router.get("/system")
async def get_system(request: Request, caller: Reader) -> SystemOut:
    admin = state(request)
    nestor, words = admin.nestor, caller.phrasebook
    heard = nestor.heard_rooms()
    return SystemOut(
        nestor=NestorOut(version=__version__),
        agent=AgentOut.of(nestor),
        restart_required=bool(admin.pending_changes),
        pending_changes=admin.pending_changes,
        components=[ComponentOut.of(p, nestor, words) for p in nestor.plugged]
        + [ComponentOut.satellite(s, heard, words) for s in nestor.pairing.satellites()],
    )


@router.get("/system/updates")
async def get_updates(request: Request, caller: Reader) -> UpdatesOut:
    return UpdatesOut.of(state(request).nestor)


@router.post("/system/updates/install", status_code=202)
async def install_update(request: Request, caller: Restarter, body: InstallIn) -> UpdatesOut:
    """Install the newest release where Nestor runs (a Python environment, never a container), check it
    accepts the configuration, then restart on it. On failure the running version stays: `failed`."""
    if not body.confirm:
        raise ApiError(400, "update_unconfirmed")
    nestor = state(request).nestor
    if nestor.updates is None:
        raise ApiError(409, "update_not_installable")
    try:
        await nestor.updates.install(body.version, by=caller.account_id or "cli")
    except ContractError:
        raise ApiError(409, "update_not_installable") from None
    return UpdatesOut.of(nestor)


@router.post("/system/restart", status_code=202)
async def restart_system(request: Request, caller: Restarter, body: RestartIn) -> RestartOut:
    """Stop everything cleanly (channels close, remote tasks are followed again after), then start
    again with the same command line — applying the configuration written since. Never automatic."""
    if not body.confirm:
        raise ApiError(400, "restart_unconfirmed")
    await state(request).nestor.restart.ask(caller.account_id or "cli")
    return RestartOut(restarting=True)
