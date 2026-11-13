"""Matrix channel: a bot account on any homeserver, through the client-server API (`/sync` long polling), a
`MessagingChannel`.

The bot joins the rooms it is invited to and answers in them. Text, pictures, voice messages, audio files and files
reach the assistant; a voice message is answered with one when the assistant has a voice. Limits: end-to-end
encrypted rooms are not read (the bot sees only their encrypted events), so a direct chat must be created without
encryption; messages sent while the bot was stopped are skipped at its next start.
"""

from nestor.adapters.channels.matrix.settings import MatrixSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "matrix", MatrixSettings, build)

__all__ = ["plugin"]
