"""Email channel: a mailbox of Nestor's own, read over IMAP (IDLE when the server has it) and answered over SMTP, a
`MessagingChannel`.

A member writes to Nestor's address; the answer comes back in the same thread (`Re:`, `In-Reply-To`), with the
pictures the assistant made. Their body (plain text, or HTML flattened) and attachments reach the assistant. Reading
reuses the IMAP connector's session and cursor (`nestor.adapters.connectors.imap`).

A sender is whoever the `From` header names, which anyone can write: by default, only mail the receiving server
authenticated reaches the assistant (`Authentication-Results` with `dmarc=pass`, or `dkim=pass` and `spf=pass`).
Turn `require_authenticated` off only for a server that adds no such header and accepts mail from nobody else (a
local bridge). Limits: mail received while Nestor was stopped is not answered; the subject of a thread is remembered
in memory only.
"""

from nestor.adapters.channels.email.settings import EmailSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "email", EmailSettings, build)

__all__ = ["plugin"]
