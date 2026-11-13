"""The home system (Home Assistant…): its state, rooms, residents, the household's ties to it, and its actions.
Configuring it is the configuration's (`home`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.home.schemas import HomeOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["home"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]


@router.get("/home")
async def get_home(request: Request, caller: Reader) -> HomeOut | None:
    """The home as it is now; `null` when no home system is plugged in."""
    nestor = state(request).nestor
    if nestor.home is None:
        return None
    plugged = next(p for p in nestor.plugged if p.component is nestor.home)
    return HomeOut.of(plugged, nestor.home, nestor, caller.phrasebook)
