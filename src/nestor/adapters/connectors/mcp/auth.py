"""Requests to a server authorised with the connection's OAuth token."""

from collections.abc import AsyncGenerator

import httpx2

from nestor.modules.connectors import Access


class ConnectionAuth(httpx2.Auth):
    """The connection's OAuth token on every request. One the server refuses before it expires (revoked, or issued
    without a lifetime) is renewed once; when it cannot be, the connection asks to be authorised again."""

    def __init__(self, access: Access) -> None:
        self._access = access

    async def async_auth_flow(self, request: httpx2.Request) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        token = await self._access.token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        request.headers["Authorization"] = f"Bearer {await self._access.token(refused=token)}"
        response = yield request
        if response.status_code == 401:
            await self._access.revoked()
