"""Email channel against a fake mailbox (IMAP side) and a fake SMTP server on the loopback: the messaging contract,
mail the server did not authenticate ignored, answers in the thread, earlier mail left alone, and no password sent
in clear to another machine."""

import asyncio
import base64
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest
from pydantic import ValidationError

from nestor.adapters.channels.email.channel import EmailChannel
from nestor.adapters.channels.email.settings import EmailSettings
from nestor.adapters.channels.email.smtp import Security
from nestor.adapters.connectors.imap.account import ImapAccount
from nestor.adapters.connectors.imap.inbound import ImapTiming
from nestor.modules.channels import Assistant, Attachment
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

from ...mailboxes import PASSWORD, FakeMailbox, ScriptedClient

NESTOR, ADA = "nestor@maison.test", "ada@maison.test"
VOUCHED = f"mx.maison.test; dkim=pass header.d=maison.test; spf=pass smtp.mailfrom={ADA}; dmarc=pass"


class FakeSmtp:
    """Just enough SMTP over asyncio: EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT; the messages kept, parsed."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []
        self.logins: list[tuple[str, str]] = []
        self.port = 0
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> "FakeSmtp":
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"220 fake ESMTP\r\n")
        while line := (await reader.readline()).decode().rstrip("\r\n"):
            verb = line.split(" ", 1)[0].upper()
            if verb == "EHLO":
                writer.write(b"250-fake\r\n250 AUTH PLAIN\r\n")
            elif verb == "AUTH":
                _, user, password = base64.b64decode(line.split(" ")[2]).split(b"\0")
                self.logins.append((user.decode(), password.decode()))
                writer.write(b"235 ok\r\n")
            elif verb == "DATA":
                writer.write(b"354 go\r\n")
                await writer.drain()
                body = b""
                while (chunk := await reader.readline()) != b".\r\n":
                    body += chunk
                self.messages.append(BytesParser(policy=policy.default).parsebytes(body))
                writer.write(b"250 queued\r\n")
            elif verb == "QUIT":
                writer.write(b"221 bye\r\n")
                await writer.drain()
                break
            else:
                writer.write(b"250 ok\r\n")
            await writer.drain()
        writer.close()


def mail(
    text: str,
    *attachments: Attachment,
    sender: str = ADA,
    vouched: bool = True,
    subject: str = "Courses",
    automatic: bool = False,
) -> bytes:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = f"Ada <{sender}>", NESTOR, subject
    message["Message-ID"] = f"<{abs(hash(text))}@maison.test>"
    if vouched:
        message["Authentication-Results"] = VOUCHED
    if automatic:
        message["Auto-Submitted"] = "auto-replied"
    message.set_content(text)
    for file in attachments:
        main, _, sub = file.media_type.partition("/")
        message.add_attachment(file.data, maintype=main, subtype=sub, filename="file")
    return bytes(message)


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(mailbox: FakeMailbox, assistant: Assistant) -> AsyncGenerator[tuple[EmailChannel, FakeSmtp]]:
    async with FakeSmtp() as smtp:
        imap = ImapAccount(host="127.0.0.1", port=993, username=mailbox.username, password=PASSWORD, tls=False)
        channel = EmailChannel(
            "email",
            address=NESTOR,
            imap=imap,
            smtp_host="127.0.0.1",
            smtp_port=smtp.port,
            smtp_security=Security.NONE,
            timing=ImapTiming(idle_s=0.05, poll_s=0.05),
            retry_delay_s=0.01,
            client=lambda account, timeout_s: ScriptedClient(mailbox, account),
        )
        task = asyncio.create_task(channel.serve(assistant))
        try:
            yield channel, smtp
        finally:
            await channel.close()
            await asyncio.wait_for(task, 2)


class EmailPlatform(Platform):
    def __init__(self, mailbox: FakeMailbox, channel: EmailChannel, smtp: FakeSmtp) -> None:
        self.mailbox, self.channel, self.smtp = mailbox, channel, smtp

    async def send(self, text: str, *attachments: Attachment) -> None:
        self.mailbox.deliver(mail(text, *attachments))

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.smtp.messages) >= count)

    def texts(self) -> list[str]:
        bodies = [m.get_body(("plain",)) for m in self.smtp.messages]
        return [str(b.get_content()).strip() for b in bodies if b is not None]

    def voices(self) -> list[bytes]:
        return []


class TestEmailMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        mailbox = FakeMailbox()
        mailbox.password = PASSWORD
        async with serving(mailbox, assistant) as (channel, smtp):
            await asyncio.sleep(0.05)  # reading starts after what is already there
            yield EmailPlatform(mailbox, channel, smtp)


def echo(message: object) -> str:
    return f"echo: {getattr(message, 'text', '').strip()}"


async def test_an_answer_stays_in_the_thread_and_mail_already_there_is_left_alone() -> None:
    mailbox = FakeMailbox()
    mailbox.password = PASSWORD
    mailbox.deliver(mail("écrit avant le démarrage"))
    async with serving(mailbox, ScriptedAssistant(echo)) as (_, smtp):
        await asyncio.sleep(0.05)
        mailbox.deliver(mail("du pain et des œufs"))
        await eventually(lambda: bool(smtp.messages))
        await asyncio.sleep(0.05)
    [answer] = smtp.messages
    assert (answer["To"], answer["Subject"]) == (ADA, "Re: Courses")
    assert answer["Auto-Submitted"] == "auto-replied", "so that a responder does not answer it"
    assert answer["In-Reply-To"] == f"<{abs(hash('du pain et des œufs'))}@maison.test>"
    assert smtp.logins == [(mailbox.username, PASSWORD)]


async def test_mail_the_server_did_not_authenticate_or_no_person_wrote_never_reaches_the_assistant() -> None:
    mailbox = FakeMailbox()
    mailbox.password = PASSWORD
    assistant = ScriptedAssistant(echo)
    async with serving(mailbox, assistant) as (_, smtp):
        await asyncio.sleep(0.05)
        mailbox.deliver(mail("ouvre le garage", vouched=False))
        mailbox.deliver(mail("Je suis en vacances jusqu'au 20.", automatic=True))
        mailbox.deliver(mail("et maintenant ?"))
        await eventually(lambda: bool(smtp.messages))
    assert [m.text.strip() for m in assistant.messages] == ["et maintenant ?"]


def test_no_password_is_sent_in_clear_to_another_machine() -> None:
    settings = {
        "address": NESTOR,
        "username": "nestor",
        "password": "x",
        "imap_host": "mail.test",
        "smtp_host": "mail.test",
        "smtp_security": "none",
    }
    with pytest.raises(ValidationError, match="in clear"):
        EmailSettings.model_validate(settings)
