"""Where the OAuth provider sends the browser back, and where the browser goes next."""

import urllib.parse

from fastapi.responses import RedirectResponse


def connected(connection_id: str) -> RedirectResponse:
    """The connection, shown in the front."""
    return RedirectResponse(f"/connections/{connection_id}?connected=1", status_code=303)


def failed(error: str, kind: str | None = None) -> RedirectResponse:
    """The failure page, with why connecting failed (`unknown_flow`, `forbidden`, `access_denied`, `provider_error`,
    `expired`, `exchange_failed`) and, when the flow is known, the service to start again with."""
    query = urllib.parse.urlencode({"error": error} | ({"kind": kind} if kind else {}))
    return RedirectResponse(f"/connections/failed?{query}", status_code=303)
