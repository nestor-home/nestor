"""Microsoft 365 accounts (Outlook mail and calendar, OneDrive, To Do) connected from the admin with the household's
own app registration.

Configuration (family `connector`, kind `microsoft`), every key optional:

    poll_interval_s: 60      # how often the inbox is read for watches
    blocked_s: 600           # wait between tries while the account must be reconnected
    retry_initial_s: 1       # first backoff delay after an outage or throttling, doubled up to retry_max_s
    retry_max_s: 300
    body_chars: 20000        # cap of a mail or a file read by outlook_mail_read and onedrive_read
    excerpt_chars: 2000      # cap of the body excerpt given to watches
    file_bytes: 20000000     # the largest OneDrive file read
"""

from nestor.adapters.connectors.microsoft.settings import MicrosoftSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["plugin"]

plugin = Plugin(Family.CONNECTOR, "microsoft", MicrosoftSettings, build)
