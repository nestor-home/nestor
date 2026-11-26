"""Satellites: paired devices people talk with in writing, aloud or both (`nestor.satellite/1`).

The channel itself needs nothing beyond Nestor; its `voice` section needs the `voice` extra
(`pip install 'nestor-home[voice]'`). This package only exposes the plugin, which reads without it; the channel, its
settings and its voice live in their modules (`nestor.adapters.channels.satellites.channel`, `.settings`, `.voice`).
"""

from nestor.adapters.channels.satellites.settings import VOICE_REQUIREMENT, SatellitesSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(
    Family.CHANNEL,
    "satellites",
    SatellitesSettings,
    build,
    requires=VOICE_REQUIREMENT,
    card=Card(
        summary="People talk to Nestor aloud or in writing through paired devices in the rooms; speaking needs the "
        "voice extra.",
        docs="satellites",
        needs=(Need.HARDWARE,),
    ),
)  # for `voice`

__all__ = ["plugin"]
