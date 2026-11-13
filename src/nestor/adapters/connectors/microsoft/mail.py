"""Outlook mail tools: search and read, nothing that changes the mailbox."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import UNTRUSTED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.microsoft.graph import GraphApi
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded

MAX_RESULTS = 20
TEXT_BODY = {"Prefer": 'outlook.body-content-type="text"'}  # Outlook flattens an HTML body itself

SEARCH = ToolSpec(
    "outlook_mail_search",
    "Search the person's Outlook mail with words (from:, subject: and received: work too). Returns sender, "
    f"subject, date, preview and id of each message, newest first. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "e.g. 'from:colissimo colis'"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
        "required": ["query"],
    },
)
READ = ToolSpec(
    "outlook_mail_read",
    f"Read one Outlook message by id (from outlook_mail_search): headers and plain-text body. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the message id"}},
        "required": ["id"],
    },
)


class MailTools:
    def __init__(self, account: str, api: Callable[[], GraphApi], *, body_chars: int) -> None:
        self._account, self._api, self._body_chars = account, api, body_chars

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=30.0),
            Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=20.0),
        )

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        query = str(arguments.get("query") or "").replace('"', " ").strip()
        if not query:
            raise ToolFailed("give words to search for")
        params = [
            ("$search", f'"{query}"'),
            ("$top", str(bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS))),
            ("$select", "id,from,subject,receivedDateTime,bodyPreview"),
        ]
        found = await ask("Outlook search", self._api().get("/me/messages", params))
        messages = [
            {
                "id": m.get("id"),
                "from": address(m.get("from")),
                "subject": m.get("subject", ""),
                "date": m.get("receivedDateTime", ""),
                "snippet": m.get("bodyPreview", ""),
            }
            for m in found.get("value", [])
            if isinstance(m, dict)
        ]
        return {"account": self._account, "query": query, "messages": messages, "note": UNTRUSTED}

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        message_id = str(arguments.get("id") or "").strip()
        if not message_id:
            raise ToolFailed("give the id of a message found with outlook_mail_search")
        api, path = self._api(), f"/me/messages/{segment(message_id)}"
        params = [
            ("$select", "id,conversationId,from,toRecipients,ccRecipients,receivedDateTime,subject,body"),
            ("$expand", "attachments($select=name,contentType,size)"),
        ]
        message = await ask("Outlook", api.get(path, params, TEXT_BODY))
        attachments = [
            {"name": a.get("name"), "type": a.get("contentType"), "size": a.get("size")}
            for a in message.get("attachments") or []
            if isinstance(a, dict)
        ]
        return {
            "id": message.get("id"),
            "thread_id": message.get("conversationId"),
            "from": address(message.get("from")),
            "to": ", ".join(address(r) for r in message.get("toRecipients") or []),
            "cc": ", ".join(address(r) for r in message.get("ccRecipients") or []),
            "date": message.get("receivedDateTime", ""),
            "subject": message.get("subject", ""),
            "body": cap(str((message.get("body") or {}).get("content") or ""), self._body_chars),
            "attachments": attachments,
            "note": UNTRUSTED,
        }


def address(recipient: Any) -> str:
    """`Name <address>`, as a mail header shows it."""
    address = (recipient or {}).get("emailAddress") or {} if isinstance(recipient, dict) else {}
    name, email = address.get("name") or "", address.get("address") or ""
    return f"{name} <{email}>" if name and name != email else email
