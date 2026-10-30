"""Satellites over WebRTC: the pairing and offer endpoints, the `nestor` data channel of each paired
device, its remote body, and the black-box conformance core drivers are checked against."""

from nestor.adapters.channels.voice.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.voice.satellites.link import RemoteBody, SatelliteLink

__all__ = ["RemoteBody", "SatelliteGateway", "SatelliteLink"]
