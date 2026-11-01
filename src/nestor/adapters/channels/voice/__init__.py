"""Realtime voice channel: a Pipecat cascade (VAD, Smart Turn, streaming STT and TTS) in front of
the assistant, reached from a browser over WebRTC.

The channel needs the `voice` extra (`pip install 'nestor-home[voice]'`). This package only exposes
what reads without it, the plugin and its settings; import the channel from its modules
(`nestor.adapters.channels.voice.channel`)."""

from nestor.adapters.channels.voice.plugin import plugin
from nestor.adapters.channels.voice.settings import ElevenLabsSettings, VoiceSettings

__all__ = ["ElevenLabsSettings", "VoiceSettings", "plugin"]
