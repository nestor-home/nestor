"""How the admin is reached: address, public URL, OAuth redirect relay, where the built front lives."""

import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from nestor.core import ContractError

DEFAULT_RELAY = "https://nestor.mathislambert.fr/redirect/oauth"
CALLBACK_PATH = "/connections/callback"
FRONT = Path(__file__).parent / "static" / "app"  # built by `pnpm build` in web/, not committed

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminSettings:
    host: str = "127.0.0.1"
    port: int = 8080
    public_url: str | None = None  # how the household's browsers reach the admin; else the URL they used
    relay_url: str = DEFAULT_RELAY  # OAuth redirect page used when the admin is not served over HTTPS
    session_ttl_s: float = 12 * 3600.0
    front_dir: Path = FRONT
    heartbeat_s: float = 15.0  # comment lines keeping a live journal stream open through proxies

    def __post_init__(self) -> None:
        for name, url in (("public_url", self.public_url), ("relay_url", self.relay_url)):
            if url is not None and urllib.parse.urlsplit(url).scheme not in ("http", "https"):
                raise ContractError(f"admin {name} must be an http(s) URL, got {url!r}")
        if urllib.parse.urlsplit(self.relay_url).scheme != "https":
            raise ContractError("admin relay_url must be served over HTTPS: providers refuse other redirect URIs")

    def base_url(self, seen: str) -> str:
        """The admin's own address: the configured public URL, else the one the browser used."""
        return (self.public_url or seen).rstrip("/")

    def redirect_uri(self, base_url: str) -> str:
        """Where the provider sends the browser back: the admin itself over HTTPS or on this very machine
        (loopback redirects are allowed in plain HTTP, RFC 8252 §7.3; Google accepts `http://localhost`),
        else the relay page."""
        host = urllib.parse.urlsplit(base_url).hostname or ""
        direct = base_url.startswith("https://") or host in LOOPBACK
        return f"{base_url}{CALLBACK_PATH}" if direct else self.relay_url
