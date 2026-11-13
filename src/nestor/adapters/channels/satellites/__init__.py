"""Satellites: paired devices people talk with in writing, aloud or both (`nestor.satellite/1`).

The channel itself needs nothing beyond Nestor; its `voice` section needs the `voice` extra
(`pip install 'nestor-home[voice]'`). This package only exposes the plugin, which reads without it; the channel, its
settings and its voice live in their modules (`nestor.adapters.channels.satellites.channel`, `.settings`, `.voice`).
"""

from nestor.adapters.channels.satellites.settings import VOICE_REQUIREMENT, SatellitesSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "satellites", SatellitesSettings, build, requires=VOICE_REQUIREMENT)  # for `voice`

__all__ = ["plugin"]
