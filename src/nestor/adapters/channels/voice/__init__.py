"""Realtime voice channel: a Pipecat cascade (VAD, Smart Turn, streaming STT and TTS) in front of
the assistant, reached from a browser over WebRTC. Requires the `voice` extra."""

from nestor.adapters.channels.voice.channel import VoiceChannel
from nestor.adapters.channels.voice.plugin import VoiceSettings, plugin
from nestor.adapters.channels.voice.providers import ElevenLabsSpeech, Speech
from nestor.adapters.channels.voice.session import SessionSettings
from nestor.adapters.channels.voice.turns import TurnSettings

__all__ = ["ElevenLabsSpeech", "SessionSettings", "Speech", "TurnSettings", "VoiceChannel", "VoiceSettings", "plugin"]
