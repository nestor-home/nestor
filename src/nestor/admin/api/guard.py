"""Bearer authentication of the JSON API. Cookies are ignored here: a browser session never opens it,
and the token never opens a page."""

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from nestor.admin.state import state


class ApiRefused(Exception):
    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status, self.error = status, error


async def bearer(request: Request) -> None:
    expected = state(request).api_token
    scheme, _, given = request.headers.get("authorization", "").partition(" ")
    if expected is None or scheme.lower() != "bearer" or not hmac.compare_digest(given.strip(), expected):
        raise ApiRefused(401, "missing or wrong admin token")


async def api_refused(request: Request, error: Exception) -> Response:
    assert isinstance(error, ApiRefused)
    headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
    return JSONResponse({"error": error.error}, status_code=error.status, headers=headers)


Authorized = Annotated[None, Depends(bearer)]
