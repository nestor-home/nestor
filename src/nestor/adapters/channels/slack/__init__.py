"""Slack channel: a Slack app in Socket Mode (events over a WebSocket, no public address needed), its answers sent
through the Web API, a `MessagingChannel`.

The bot answers direct messages, and messages that mention it in channels. Text, pictures, audio clips and files
reach the assistant; answers go back written, with the pictures the assistant made. The app needs Socket Mode, an
app-level token (`connections:write`), and a bot token with `chat:write`, `files:read`, `files:write`, `im:history`
and `app_mentions:read`, subscribed to the `message.im` and `app_mention` events. Limits: a voice message is answered
in writing; Slack shows no "typing…" for apps.
"""

from nestor.adapters.channels.slack.settings import SlackSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "slack", SlackSettings, build)

__all__ = ["plugin"]
