"""The IMAP operations Nestor needs, behind an interface it owns (the aioimaplib binding is one implementation).

Everything is read only: messages are fetched with `BODY.PEEK`, so reading never marks them as seen.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from nestor.core import ProviderError

PROVIDER = "imap"


class MailboxUnavailable(ProviderError):
    """The server could not be reached, dropped the connection, timed out or answered unexpectedly."""

    def __init__(self, message: str) -> None:
        super().__init__(PROVIDER, message, transient=True)


class LoginRefused(ProviderError):
    """The server refused the credentials: only the person can fix it (often: an app password is needed)."""

    def __init__(self, message: str) -> None:
        super().__init__(PROVIDER, message, transient=False)


@dataclass(frozen=True, slots=True)
class Selected:
    """A selected folder: UIDs are only comparable while `uidvalidity` stays the same."""

    uidvalidity: int
    uidnext: int | None  # the UID the next message will get at least, when the server says


@dataclass(frozen=True, slots=True)
class Fetched:
    uid: int
    data: bytes  # the fetched section (whole message or headers), possibly cut at the requested size


class MailboxClient(ABC):
    """One IMAP connection. Every method raises `MailboxUnavailable` (or `LoginRefused` for `login`)."""

    @abstractmethod
    async def open(self) -> None:
        """Connect and wait for the server's greeting."""

    @abstractmethod
    async def login(self, username: str, password: str) -> None: ...

    @abstractmethod
    async def select(self, folder: str) -> Selected: ...

    @abstractmethod
    async def search(self, *criteria: str, charset: str | None = None) -> list[int]:
        """UIDs matching `criteria` (`UID SEARCH`), in the server's order."""

    @abstractmethod
    async def fetch(self, uids: Sequence[int], section: str) -> list[Fetched]:
        """`UID FETCH` of `section` (`BODY.PEEK[]<0.N>`…) for these UIDs; expunged ones are simply absent."""

    @property
    @abstractmethod
    def supports_idle(self) -> bool: ...

    @abstractmethod
    async def wait_for_change(self, timeout_s: float) -> None:
        """Return when the server reports a change to the folder (IDLE), or after `timeout_s` at most."""

    @abstractmethod
    async def close(self) -> None:
        """Log out and release the connection; never raises."""
