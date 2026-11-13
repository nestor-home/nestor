"""A fake DNS for adapters that check where a name resolves before fetching it (`adapters/common/web.py`)."""

import ipaddress
import socket
from collections.abc import Mapping

import pytest


def resolve(monkeypatch: pytest.MonkeyPatch, names: Mapping[str, str]) -> None:
    """Names resolve to the address `names` gives, addresses to themselves, anything else to nothing."""

    def getaddrinfo(host: str, port: int | None, *args: object, **kwargs: object) -> list:
        try:
            address = str(ipaddress.ip_address(host.strip("[]")))
        except ValueError:
            if host not in names:
                raise socket.gaierror(socket.EAI_NONAME, "not found") from None
            address = names[host]
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
