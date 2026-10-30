"""What a transport adapter implements to let satellites in."""

from abc import ABC, abstractmethod

from nestor.modules.journal import Journal
from nestor.modules.satellites.service import Pairing


class SatelliteHost(ABC):
    """A component that accepts satellite connections (the voice channel's WebRTC gateway, later a
    WebSocket one). The runtime hands it the pairing service, which decides who may connect, and the
    journal, where connections and observations are written."""

    @abstractmethod
    def host_satellites(self, pairing: Pairing, journal: Journal) -> None:
        """Called once, before the component serves."""
