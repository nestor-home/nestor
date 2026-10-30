"""How the admin is reached and protected: address, public URL, OAuth redirect relay, password hash."""

import urllib.parse
from dataclasses import dataclass

from nestor.admin.auth.passwords import check_hash
from nestor.core import ContractError

DEFAULT_RELAY = "https://nestor.mathislambert.fr/redirect/oauth"
CALLBACK_PATH = "/connections/callback"


LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminSettings:
    password_hash: str  # from `nestor admin-password`
    host: str = "127.0.0.1"
    port: int = 8080
    public_url: str | None = None  # how the household's browsers reach the admin; else the URL they used
    relay_url: str = DEFAULT_RELAY  # OAuth redirect page used when the admin is not served over HTTPS
    session_ttl_s: float = 12 * 3600.0

    def __post_init__(self) -> None:
        check_hash(self.password_hash)
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
