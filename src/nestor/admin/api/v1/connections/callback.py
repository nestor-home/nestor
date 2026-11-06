"""Where the OAuth provider sends the browser back, and where the browser goes next."""

from fastapi.responses import RedirectResponse


def connected(connection_id: str) -> RedirectResponse:
    """The connection, shown in the front."""
    return RedirectResponse(f"/connections/{connection_id}?connected=1", status_code=303)


def failed(code: str) -> RedirectResponse:
    """The catalogue, with why connecting failed (`unknown_flow`, `forbidden`, `access_denied`…)."""
    return RedirectResponse(f"/connections?oauth_error={code}", status_code=303)
