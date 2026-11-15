"""The executors Nestor hands tasks to, and their keys for its MCP server: made (shown once), renewed, revoked.

Reading needs `system.read`; making or revoking a key, `config.manage`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.executors.schemas import ExecutorOut, ExecutorsOut, IssuedKeyOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.cognition.delegation import ExecutorKeys

router = APIRouter(tags=["executors"])
Reader = Annotated[Caller, Depends(allowed(Scope.SYSTEM_READ))]
Manager = Annotated[Caller, Depends(allowed(Scope.CONFIG_MANAGE, local=True))]


@router.get("/executors")
async def list_executors(request: Request, caller: Reader) -> ExecutorsOut:
    nestor = state(request).nestor
    keys = nestor.executor_keys
    issued = dict(await keys.status()) if keys else {}
    return ExecutorsOut(url=keys.url if keys else None, executors=[ExecutorOut.of(e, issued) for e in nestor.executors])


@router.post("/executors/{name}/key")
async def issue_executor_key(request: Request, caller: Manager, name: str) -> IssuedKeyOut:
    """A new key for the executor, replacing its last: shown only in this answer."""
    keys = _keys(request, name)
    return IssuedKeyOut(key=await keys.issue(name, by=caller.account_id), url=keys.url)


@router.delete("/executors/{name}/key", status_code=204)
async def revoke_executor_key(request: Request, caller: Manager, name: str) -> Response:
    await _keys(request, name).revoke(name, by=caller.account_id)
    return Response(status_code=204)


def _keys(request: Request, name: str) -> ExecutorKeys:
    nestor = state(request).nestor
    if not any(e.name == name for e in nestor.executors):
        raise not_found("executor_unknown")
    if nestor.executor_keys is None:
        raise ApiError(409, "executors_unreachable")
    return nestor.executor_keys
