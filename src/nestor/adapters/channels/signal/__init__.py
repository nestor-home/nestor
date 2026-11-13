"""Signal channel: a number registered with signal-cli, reached through signal-cli-rest-api (its `normal` or `native`
mode, which `/v1/receive` long-polls; `native` starts no JVM at each poll), a `MessagingChannel`.

Direct messages and groups reach the assistant, with their pictures, voice notes, audio files and files; answers go
back written, with the pictures the assistant made. Limits: a voice message is answered in writing (Signal plays AAC
voice notes, the assistant records OGG/Opus); signal-cli-rest-api's `json-rpc` mode, which only streams over a
WebSocket, is not supported.
"""

from nestor.adapters.channels.signal.settings import SignalSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "signal", SignalSettings, build)

__all__ = ["plugin"]
