"""The email channel: new mail read from the mailbox over IMAP, answered in the same thread over SMTP."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import make_msgid, parseaddr
from typing import Any

from nestor.adapters.channels.email.authentication import authenticated, automatic
from nestor.adapters.channels.email.smtp import Security, send
from nestor.adapters.channels.messaging import Incoming, MessagingChannel, Pending, files_sent
from nestor.adapters.connectors.imap.account import ImapAccount, session
from nestor.adapters.connectors.imap.aioimap import AioImapClient
from nestor.adapters.connectors.imap.client import MailboxClient
from nestor.adapters.connectors.imap.inbound import ImapTiming, UidCursor, folder_end, newer
from nestor.adapters.connectors.imap.message import MailMessage
from nestor.core import ProviderError
from nestor.modules.channels import Address, Answer, Attachment, AttachmentKind, Sender

logger = logging.getLogger(__name__)

TIMING = ImapTiming(fetch_bytes=25 * 1024 * 1024)  # a message is fetched with its attachments


class EmailChannel(MessagingChannel):
    name = "email"
    brand = "email"
    sends = frozenset({AttachmentKind.IMAGE, AttachmentKind.FILE, AttachmentKind.AUDIO})

    def __init__(
        self,
        channel_id: str,
        *,
        address: str,
        imap: ImapAccount,
        smtp_host: str,
        smtp_port: int = 465,
        smtp_security: Security = Security.TLS,
        require_authenticated: bool = True,
        timing: ImapTiming = TIMING,
        client: Callable[[ImapAccount, float], MailboxClient] = AioImapClient,
        **common: Any,
    ) -> None:
        """`address`: Nestor's own, where members write. `common`: what every `MessagingChannel` takes."""
        super().__init__(channel_id, **common)
        self._address, self._imap, self._client = address.lower(), imap, client
        self._smtp = (smtp_host, smtp_port, smtp_security)
        self._require_authenticated = require_authenticated
        self._timing = timing
        self._cursor: UidCursor | None = None  # where reading resumes after a reconnection, in memory
        self._threads: dict[str, tuple[str, str]] = {}  # by correspondent: the subject and Message-ID to answer

    async def receive(self) -> AsyncIterator[Incoming]:
        while not self.closed:
            try:
                async with session(self._imap, self._client, self._timing.timeout_s) as (client, selected):
                    cursor = self._cursor
                    if cursor is None or cursor.uidvalidity != selected.uidvalidity:
                        # mail there before Nestor started, or before the folder was rebuilt, is not answered
                        cursor = self._cursor = await folder_end(client, selected)
                    self.reached()
                    while not self.closed:
                        for uid in await newer(client, cursor):
                            fetched = await client.fetch([uid], f"BODY.PEEK[]<0.{self._timing.fetch_bytes}>")
                            cursor = self._cursor = UidCursor(cursor.uidvalidity, uid)
                            if fetched and (incoming := self._incoming(fetched[0].data)) is not None:
                                yield incoming
                        wait = self._timing.idle_s if client.supports_idle else self._timing.poll_s
                        await self.unless_closed(client.wait_for_change(wait))
            except ProviderError as error:
                await self.retry_later(error)

    async def deliver(self, conversation: str, answer: Answer) -> None:
        """One mail in the thread, with its files; the text alone when the server refuses them."""
        files = answer.files
        if files and await files_sent(self, conversation, files, self._send(conversation, answer.text, files)):
            return
        await self._send(conversation, answer.text, ())

    async def _send(self, conversation: str, text: str, files: tuple[Attachment, ...]) -> None:
        subject, replying_to = self._threads.get(conversation, ("", ""))
        message = EmailMessage(policy=policy.SMTP)
        message["From"], message["To"] = self._address, conversation
        message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}" if subject else "Nestor"
        message["Message-ID"] = make_msgid(domain=self._address.rpartition("@")[2] or None)
        message["Auto-Submitted"] = "auto-replied"  # RFC 3834: responders do not answer it
        if replying_to:
            message["In-Reply-To"] = message["References"] = replying_to
        message.set_content(text)
        for file in files:
            main, _, sub = file.media_type.partition("/")
            message.add_attachment(file.data, maintype=main, subtype=sub, filename=file.file_name)
        host, port, security = self._smtp
        await asyncio.to_thread(
            send,
            message,
            host=host,
            port=port,
            security=security,
            username=self._imap.username,
            password=self._imap.password,
            timeout_s=self._timing.timeout_s,
        )

    def _incoming(self, raw: bytes) -> Incoming | None:
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        name, sender = parseaddr(str(parsed.get("From", "")))
        sender = sender.lower()
        if not sender or sender == self._address or automatic(parsed):
            return None  # its own mail, or mail no person wrote: answering a responder would loop
        if self._require_authenticated and not authenticated(parsed, sender):
            logger.warning("email: mail claiming to be from %s was not authenticated by the server: ignored", sender)
            return None
        message = MailMessage.of(parsed)
        self._threads[sender] = (message.subject, str(parsed.get("Message-ID", "")))
        files = [
            Pending.ready(payload, part.get_content_type(), name=part.get_filename())
            for part in parsed.iter_attachments()
            if isinstance(payload := part.get_payload(decode=True), bytes)
        ]
        return Incoming(
            address=Address(self.channel_id, sender),
            sender=Sender(sender, name or None),
            text=message.body,
            files=tuple(files),
        )
