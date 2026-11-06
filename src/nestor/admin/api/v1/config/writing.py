"""Writing the configuration from the admin: validated first, refused with its located problems, then pending
until a person restarts."""

from typing import Any

from nestor.admin.api.v1.config.schemas import DiffOut, WrittenOut
from nestor.admin.api.v1.errors import ApiError, ProblemOut
from nestor.admin.api.v1.security import Caller
from nestor.admin.state import AdminState
from nestor.runtime.editing import ConfigEditor, EditRefused


async def write(
    admin: AdminState, editor: ConfigEditor, caller: Caller, document: dict[str, Any], restored: str | None = None
) -> WrittenOut:
    """422 `config_invalid` with `problems` when it cannot be used: nothing is written then."""
    try:
        diff = await editor.write(document, by=caller.account_id or "cli", restored=restored)
    except EditRefused as refused:
        problems = [ProblemOut.of(p, caller.phrasebook).model_dump() for p in refused.problems]
        raise ApiError(422, "config_invalid", problems=problems, count=len(problems)) from None
    admin.pending_changes = sorted({*admin.pending_changes, *diff.paths})
    return WrittenOut(diff=DiffOut.of(diff), restart_required=True, pending_changes=admin.pending_changes)
