"""IMAP tools for the central agent: search and read the connected folder, never changing it."""

from collections.abc import Awaitable, Callable, Mapping, Sequence

from nestor.adapters.connectors.common import UNTRUSTED, cap
from nestor.adapters.connectors.imap.account import ClientFactory, ImapAccount, session
from nestor.adapters.connectors.imap.message import MailMessage
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed
from nestor.modules.connectors import Connection

MAX_RESULTS = 30
HEADERS = "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)]"

SEARCH = ToolSpec(
    "imap_mail_search",
    "Search the person's mailbox: the most recent messages whose subject or sender contains `text` "
    f"(all recent messages without it). Returns uid, sender, subject and date. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "words of the subject or sender, e.g. 'colissimo'"},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
    },
)
READ = ToolSpec(
    "imap_mail_read",
    f"Read one message by uid (from imap_mail_search): headers and plain-text body. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {"uid": {"type": "integer", "description": "the message uid"}},
        "required": ["uid"],
    },
)


class ImapTools:
    def __init__(
        self,
        connection: Connection,
        account: Callable[[], Awaitable[ImapAccount]],
        factory: ClientFactory,
        *,
        timeout_s: float,
        fetch_bytes: int,
        body_chars: int,
    ) -> None:
        self._connection, self._account, self._factory = connection, account, factory
        self._timeout_s, self._fetch_bytes, self._body_chars = timeout_s, fetch_bytes, body_chars

    def tools(self) -> Sequence[Tool]:
        budget = 3 * self._timeout_s  # connect, log in, then the command itself
        return (
            Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=budget),
            Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=budget),
        )

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        text = " ".join(str(arguments.get("text") or "").split())
        limit = _bounded(arguments.get("limit"), default=10, maximum=MAX_RESULTS)
        criteria = ("OR", "SUBJECT", _quoted(text), "FROM", _quoted(text)) if text else ("ALL",)
        try:
            async with session(await self._account(), self._factory, self._timeout_s) as (client, _):
                uids = sorted(await client.search(*criteria, charset="UTF-8" if text else None))[-limit:]
                fetched = await client.fetch(uids, HEADERS)
        except ProviderError as error:
            raise ToolFailed(f"the mailbox {self._connection.account} could not be searched: {error}") from None
        newest_first = sorted(fetched, key=lambda f: f.uid, reverse=True)
        headers = [(f.uid, MailMessage.parse(f.data)) for f in newest_first]
        messages = [{"uid": uid, "from": m.sender, "subject": m.subject, "date": m.date} for uid, m in headers]
        return {"account": self._connection.account, "messages": messages, "note": UNTRUSTED}

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        uid = arguments.get("uid")
        if isinstance(uid, str) and uid.strip().isdigit():
            uid = int(uid)
        if not isinstance(uid, int) or isinstance(uid, bool) or uid < 1:
            raise ToolFailed("give the uid of a message found with imap_mail_search")
        try:
            async with session(await self._account(), self._factory, self._timeout_s) as (client, _):
                fetched = await client.fetch([uid], f"BODY.PEEK[]<0.{self._fetch_bytes}>")
        except ProviderError as error:
            raise ToolFailed(f"the mailbox {self._connection.account} could not be read: {error}") from None
        if not fetched:
            raise ToolFailed(f"no message with uid {uid} in {self._connection.account}")
        message = MailMessage.parse(fetched[0].data)
        return {
            "uid": uid,
            "from": message.sender,
            "to": message.to,
            "date": message.date,
            "subject": message.subject,
            "body": cap(message.body, self._body_chars),
            "attachments": list(message.attachments),
            "note": UNTRUSTED,
        }


def _quoted(text: str) -> str:
    """An IMAP quoted string (RFC 3501); non-ASCII is sent as UTF-8 with `CHARSET UTF-8`."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bounded(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return max(1, min(int(value), maximum))
    except ValueError:
        return default
