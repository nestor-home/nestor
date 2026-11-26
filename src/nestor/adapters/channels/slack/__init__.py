"""Slack channel: a Slack app in Socket Mode (events over a WebSocket, no public address needed), its answers sent
through the Web API, a `MessagingChannel`.

The bot answers direct messages, and messages that mention it in channels. Text, pictures, audio clips and files
reach the assistant; answers go back written, with the files the assistant made (pictures, documents, audio files),
each under its name. The app needs Socket Mode, an app-level token (`connections:write`), and a bot token with
`chat:write`, `files:read`, `files:write`, `im:history` and `app_mentions:read`, subscribed to the `message.im` and
`app_mention` events. Limits: a voice message is answered in writing; Slack shows no "typing…" for apps.
"""

from nestor.adapters.channels.slack.settings import SlackSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(
    Family.CHANNEL,
    "slack",
    SlackSettings,
    build,
    card=Card(
        summary="People write to Nestor on Slack, in direct messages or by mentioning its app.",
        docs="channels#choose-channels",
        needs=(Need.KEY,),
    ),
)

__all__ = ["plugin"]
