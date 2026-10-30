"""Gmail tools for the central agent: search and read, nothing that changes the mailbox."""

import asyncio
from collections.abc import Callable, Mapping, Sequence

from nestor.adapters.connectors.common import UNTRUSTED, cap
from nestor.adapters.connectors.google.api import GmailApi, GmailError
from nestor.adapters.connectors.google.mime import GmailMessage
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed
from nestor.modules.connectors import Connection

MAX_RESULTS = 20
SUMMARY_HEADERS = ("From", "Subject", "Date")

SEARCH = ToolSpec(
    "google_mail_search",
    "Search the person's Gmail with Gmail query syntax (from:, subject:, newer_than:7d, is:unread…). "
    f"Returns sender, subject, date, snippet and id of each message. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query, e.g. 'from:colissimo newer_than:3d'"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
        "required": ["query"],
    },
)
READ = ToolSpec(
    "google_mail_read",
    f"Read one Gmail message by id (from google_mail_search): headers and plain-text body. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the message id"}},
        "required": ["id"],
    },
)


class GmailTools:
    """The tools of one connected Gmail account."""

    def __init__(self, connection: Connection, api: Callable[[], GmailApi], *, body_chars: int) -> None:
        self._connection, self._api, self._body_chars = connection, api, body_chars

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=30.0),
            Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=20.0),
        )

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        query = str(arguments.get("query", "")).strip()
        limit = _bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS)
        api = self._api()
        try:
            ids = await api.search(query, limit)
            found = await asyncio.gather(*(api.message(i, metadata=SUMMARY_HEADERS) for i in ids))
        except ProviderError as error:
            raise ToolFailed(f"Gmail search failed for {self._connection.account}: {error}") from None
        messages = [
            {
                "id": m.id,
                "from": m.header("from"),
                "subject": m.subject,
                "date": m.header("date"),
                "snippet": m.snippet,
            }
            for m in map(GmailMessage.of, found)
        ]
        return {"account": self._connection.account, "query": query, "messages": messages, "note": UNTRUSTED}

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        message_id = str(arguments.get("id", "")).strip()
        if not message_id:
            raise ToolFailed("give the id of a message found with google_mail_search")
        try:
            message = GmailMessage.of(await self._api().message(message_id))
        except GmailError as error:
            if error.status in (400, 404):
                raise ToolFailed(f"no message {message_id!r} in {self._connection.account}") from None
            raise ToolFailed(f"Gmail could not be read: {error}") from None
        except ProviderError as error:
            raise ToolFailed(f"Gmail could not be read: {error}") from None
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "from": message.header("from"),
            "to": message.header("to"),
            "cc": message.header("cc"),
            "date": message.header("date"),
            "subject": message.subject,
            "body": cap(message.text() or message.snippet, self._body_chars),
            "attachments": message.attachments(),
            "note": UNTRUSTED,
        }


def _bounded(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return max(1, min(int(value), maximum))
    except ValueError:
        return default
