"""What a transport adapter implements to let satellites in."""

from abc import ABC, abstractmethod

from nestor.modules.journal import Journal
from nestor.modules.satellites.service import Pairing


class SatelliteHost(ABC):
    """A component that accepts satellite connections (the voice channel's WebRTC gateway, later a
    WebSocket one). The runtime hands it the pairing service, which decides who may connect, and the
    journal, where connections and observations are written. While it holds a paired device's link,
    it registers how to reach it with `Pairing.online`, so a person can ask it to identify itself."""

    @abstractmethod
    def host_satellites(self, pairing: Pairing, journal: Journal) -> None:
        """Called once, before the component serves."""

    @abstractmethod
    def satellite_url(self, seen_as: str) -> str | None:
        """The base URL devices reach this host at (it goes into pairing URIs), `None` when it serves
        none. `seen_as` is the host name the household reaches Nestor by (the admin's, as the browser
        sees it): a host listening on every interface is reached by that name."""
