"""Telegram channel: a bot reached through the Bot HTTP API with long polling, a `MessagingChannel`.

Text, photos, voice messages, audio files and documents reach the assistant (with their caption); a voice message is
answered with one when the assistant has a voice. Limits: the Bot API serves files up to 20 MB, larger ones are left
out; stickers, videos and locations are ignored; updates are acknowledged in memory, so the last batch received before
a stop is delivered again at the next start.
"""

from nestor.adapters.channels.telegram.settings import TelegramSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "telegram", TelegramSettings, build)

__all__ = ["plugin"]
