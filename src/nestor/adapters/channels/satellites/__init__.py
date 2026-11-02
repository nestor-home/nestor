"""Satellites: paired devices people talk with in writing, aloud or both (`nestor.satellite/1`).

The channel itself needs nothing beyond Nestor; its `voice` section needs the `voice` extra
(`pip install 'nestor-home[voice]'`). This package only exposes what reads without it, the plugin and
its settings; import the channel from its modules (`nestor.adapters.channels.satellites.channel`)."""

from nestor.adapters.channels.satellites.plugin import plugin
from nestor.adapters.channels.satellites.settings import ElevenLabsSettings, SatellitesSettings, VoiceSettings

__all__ = ["ElevenLabsSettings", "SatellitesSettings", "VoiceSettings", "plugin"]
