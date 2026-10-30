"""The admin's JSON API, used by the local `nestor` command line with the bearer token of `admin.token`."""

from nestor.admin.api.guard import ApiRefused, api_refused
from nestor.admin.api.satellites import router as satellites

__all__ = ["ApiRefused", "api_refused", "satellites"]
