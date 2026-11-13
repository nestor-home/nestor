"""ntfy channel: a notification pushed to a phone through ntfy (ntfy.sh, or a server of one's own), on a topic
the person subscribed to in the ntfy app.

A person's `reach` names their topic (`ntfy:<topic>`): reminders, a task's result, a message passed on arrive as
notifications, with the pictures the assistant made. Nobody answers through it. A topic on the public server is
readable by whoever knows its name: pick one nobody would guess, or use a server with access control and a token.
"""

from nestor.adapters.channels.ntfy.settings import NtfySettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "ntfy", NtfySettings, build)

__all__ = ["plugin"]
