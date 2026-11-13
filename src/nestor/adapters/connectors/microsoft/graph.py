"""The Microsoft Graph calls Nestor makes for one account (https://learn.microsoft.com/graph/api/overview).

Errors follow https://learn.microsoft.com/graph/errors: throttling (429), server errors and 401 (an access token
refused, refreshed by `Access.token()` once expired) are worth retrying; the body names the error by its `code`.
"""

from typing import Any

import httpx

from nestor.adapters.connectors.common.api import BearerApi, StatusError
from nestor.adapters.connectors.common.tools import ask

GRAPH = "https://graph.microsoft.com/v1.0"
PROVIDER = "microsoft"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

type Json = dict[str, Any]


class GraphError(StatusError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(PROVIDER, status, code, message, transient=status == 401)  # a token refreshed by `Access`

    @classmethod
    def of(cls, response: httpx.Response) -> "GraphError":
        try:
            error = response.json()["error"]
            return cls(response.status_code, str(error.get("code", "")), str(error.get("message", "")))
        except (ValueError, KeyError, TypeError, AttributeError):
            return cls(response.status_code, "", response.reason_phrase)


def new_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    # a file's content redirects to a pre-signed address, which httpx reaches without the token
    return httpx.AsyncClient(base_url=GRAPH, timeout=TIMEOUT, transport=transport, follow_redirects=True)


class GraphApi(BearerApi):
    provider = PROVIDER

    def error(self, response: httpx.Response) -> GraphError:
        return GraphError.of(response)


async def mailbox_zone(api: GraphApi, known: dict[str, str]) -> str:
    """The time zone of the person's mailbox, asked once: where their days start, how Outlook and To Do show times."""
    if "zone" not in known:
        found = await ask("Outlook", api.get("/me/mailboxSettings/timeZone"))
        known["zone"] = str(found.get("value") or "UTC")
    return known["zone"]


def in_zone(zone: str) -> dict[str, str]:
    """The header that has Graph answer times in `zone` rather than in UTC."""
    return {"Prefer": f'outlook.timezone="{zone}"'}
