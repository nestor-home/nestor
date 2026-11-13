"""Discord channel: a bot application, its messages received over the Gateway (WebSocket) and its answers sent over the
HTTP API, a `MessagingChannel`.

The bot answers direct messages, and messages that mention it in a server's channels. Text, pictures, voice
messages, audio files and files reach the assistant; answers go back written, split under Discord's 2000 characters,
with the pictures the assistant made. Its application needs the Message Content intent (Developer Portal, Bot).
Limits: a voice message is answered in writing (Discord's voice messages need a waveform this channel does not
compute); a dropped connection is reconnected rather than resumed, so messages sent during the gap are missed.
"""

from nestor.adapters.channels.discord.settings import DiscordSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "discord", DiscordSettings, build)

__all__ = ["plugin"]
