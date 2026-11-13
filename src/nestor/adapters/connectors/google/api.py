"""The Google API calls Nestor makes: `GoogleApi` for any of Google's JSON APIs, `GmailApi` for the mail
(https://developers.google.com/workspace/gmail/api/reference/rest).

Errors follow https://developers.google.com/workspace/gmail/api/guides/handle-errors, the same for every Google API:
rate limits (429, 403 `rateLimitExceeded`/`userRateLimitExceeded`) and server errors are worth retrying with a
backoff; 401 means the access token was refused (it is refreshed by `Access.token()` once expired).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from nestor.adapters.connectors.common.api import BearerApi, StatusError, segment

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
PROVIDER = "google"
RATE_LIMITS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

type Json = dict[str, Any]


class GoogleError(StatusError):
    """Google answered with an error; `status` and `reason` say which."""

    def __init__(self, status: int, reason: str, message: str) -> None:
        refused_or_limited = status == 401 or (status == 403 and reason in RATE_LIMITS)  # a token refreshed, a rate
        super().__init__(PROVIDER, status, reason, message, transient=refused_or_limited)

    @classmethod
    def of(cls, response: httpx.Response) -> "GoogleError":
        try:
            error = response.json()["error"]
            reasons = [e.get("reason", "") for e in error.get("errors", []) if isinstance(e, dict)]
            return cls(response.status_code, (reasons or [""])[0] or str(error.get("status", "")), error["message"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return cls(response.status_code, "", response.reason_phrase)


@dataclass(frozen=True, slots=True)
class Profile:
    email: str
    history_id: str


@dataclass(frozen=True, slots=True)
class HistoryPage:
    added: tuple[str, ...]  # ids of messages added, oldest first
    history_id: str  # the mailbox's current history id
    next_page: str | None


def new_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, transport=transport)


class GoogleApi(BearerApi):
    provider = PROVIDER

    def error(self, response: httpx.Response) -> GoogleError:
        return GoogleError.of(response)


class GmailApi(GoogleApi):
    async def profile(self) -> Profile:
        found = await self._gmail("profile")
        return Profile(email=str(found.get("emailAddress", "")), history_id=str(found.get("historyId", "")))

    async def history(self, start: str, page: str | None = None) -> HistoryPage:
        """Messages added to the inbox after history id `start`; `GoogleError` 404 when `start` is too old."""
        params = [("startHistoryId", start), ("historyTypes", "messageAdded"), ("labelId", "INBOX")]
        found = await self._gmail("history", [*params, ("pageToken", page)] if page else params)
        added = [
            str(entry["message"]["id"])
            for record in found.get("history", [])
            for entry in record.get("messagesAdded", [])
            if isinstance(entry.get("message"), dict) and "id" in entry["message"]
        ]
        return HistoryPage(tuple(added), str(found.get("historyId", start)), found.get("nextPageToken"))

    async def message(self, message_id: str, *, metadata: Sequence[str] | None = None) -> Json:
        """One message, `format=full`, or only the named headers when `metadata` is given."""
        if metadata is None:
            return await self._gmail(f"messages/{segment(message_id)}", [("format", "full")])
        return await self._gmail(
            f"messages/{segment(message_id)}", [("format", "metadata"), *(("metadataHeaders", h) for h in metadata)]
        )

    async def search(self, query: str, limit: int) -> list[str]:
        found = await self._gmail("messages", [("q", query), ("maxResults", str(limit))])
        return [str(m["id"]) for m in found.get("messages", []) if isinstance(m, dict) and "id" in m]

    async def _gmail(self, path: str, params: Sequence[tuple[str, str]] = ()) -> Json:
        return await self.get(f"{GMAIL}/{path}", params)
