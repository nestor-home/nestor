"""What the pairing service's answers mean for the API: who approved each satellite, and the errors a device
that cannot be reached stands for."""

from nestor.admin.api.v1.errors import ApiError, ErrorCode, not_found
from nestor.admin.state import AdminState
from nestor.core import PersonId
from nestor.modules.satellites import DeviceUnavailable, SatellitePaired


async def approvers(admin: AdminState) -> dict[str, PersonId | None]:
    """Who approved each paired device, as journaled (the latest pairing wins)."""
    return {e.device.id: e.approved_by for e in await admin.nestor.journal.history(SatellitePaired)}


def unavailable(
    error: DeviceUnavailable, unknown: ErrorCode, *, unsupported: ErrorCode = "identify_unsupported"
) -> ApiError:
    if error.reason == "unknown":
        return not_found(unknown)
    return ApiError(409, unsupported if error.reason == "unsupported" else "satellite_offline")
