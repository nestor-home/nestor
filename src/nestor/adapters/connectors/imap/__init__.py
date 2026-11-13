"""Mailboxes reached over IMAP with an application password, read only.

Configuration (family `connector`, kind `imap`), every key optional:

    timeout_s: 30            # every IMAP command
    idle_s: 1500             # IDLE renewed after this long (servers drop it after 29 minutes at most)
    poll_s: 60               # between checks when the server has no IDLE
    fetch_bytes: 1000000     # a message is read up to this size
    blocked_s: 600           # wait between tries while the credentials are refused
    retry_initial_s: 1       # first backoff delay after an outage, doubled up to retry_max_s
    retry_max_s: 300
    body_chars: 20000        # cap of a body read by imap_mail_read
    excerpt_chars: 2000      # cap of the body excerpt given to watches
"""

from nestor.adapters.connectors.imap.settings import ImapSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["plugin"]

plugin = Plugin(Family.CONNECTOR, "imap", ImapSettings, build)
