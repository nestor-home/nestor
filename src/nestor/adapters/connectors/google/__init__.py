"""Google accounts (Gmail, Calendar, Drive, Contacts, Tasks) connected from the admin with the household's own OAuth
client.

Configuration (family `connector`, kind `google`), every key optional:

    poll_interval_s: 30      # how often the inbox history is read for watches
    blocked_s: 600           # wait between tries while the account must be reconnected
    retry_initial_s: 1       # first backoff delay after an outage or a rate limit, doubled up to retry_max_s
    retry_max_s: 300
    body_chars: 20000        # cap of a mail or a file read by google_mail_read and google_drive_read
    file_bytes: 20000000     # the largest Drive file read
    excerpt_chars: 2000      # cap of the body excerpt given to watches
"""

from nestor.adapters.connectors.google.settings import GoogleSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["plugin"]

plugin = Plugin(Family.CONNECTOR, "google", GoogleSettings, build)
