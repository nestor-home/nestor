"""Admin sessions, kept in memory: a restart signs everyone out, which is acceptable for one household.

The cookie carries a random session id and its HMAC signature; everything else (the account, the
CSRF token, messages to show) stays on the server. A session belongs to one account and can be
revoked with every other session of that account.
"""

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True, kw_only=True)
class Session:
    id: str
    csrf: str
    expires_at: float
    account_id: str | None = None  # None: anonymous (the legacy login form's own CSRF token)
    notices: list[str] = field(default_factory=list)  # shown once, on the next server-rendered page

    @property
    def authenticated(self) -> bool:
        return self.account_id is not None

    def notify(self, text: str) -> None:
        self.notices.append(text)

    def take_notices(self) -> list[str]:
        notices, self.notices = self.notices, []
        return notices


class SessionStore:
    def __init__(self, *, ttl_s: float, limit: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s, self._limit, self._clock = ttl_s, limit, clock
        self._key = secrets.token_bytes(32)
        self._sessions: dict[str, Session] = {}

    def open(self, account_id: str | None = None) -> Session:
        """A new session, always with a fresh id: a session id planted before signing in is worth nothing."""
        self._evict()
        session = Session(
            id=secrets.token_urlsafe(32),
            csrf=secrets.token_urlsafe(32),
            expires_at=self._clock() + self.ttl_s,
            account_id=account_id,
        )
        self._sessions[session.id] = session
        return session

    def find(self, cookie: str | None) -> Session | None:
        if not cookie:
            return None
        session_id, _, signature = cookie.partition(".")
        if not hmac.compare_digest(signature, self._sign(session_id)):
            return None
        session = self._sessions.get(session_id)
        if session is None or not self.alive(session):
            self._sessions.pop(session_id, None)
            return None
        return session

    def alive(self, session: Session) -> bool:
        """Still open: neither closed, revoked nor expired."""
        return self._sessions.get(session.id) is session and session.expires_at > self._clock()

    def cookie(self, session: Session) -> str:
        return f"{session.id}.{self._sign(session.id)}"

    def close(self, session: Session) -> None:
        self._sessions.pop(session.id, None)

    def revoke(self, account_id: str, *, keep: Session | None = None) -> int:
        """Close every session of the account but `keep`; how many were closed."""
        doomed = [i for i, s in self._sessions.items() if s.account_id == account_id and s is not keep]
        for session_id in doomed:
            del self._sessions[session_id]
        return len(doomed)

    def _sign(self, session_id: str) -> str:
        return hmac.new(self._key, session_id.encode(), hashlib.sha256).hexdigest()

    def _evict(self) -> None:
        now = self._clock()
        for session_id in [i for i, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[session_id]
        while len(self._sessions) >= self._limit:
            # oldest first (dicts keep insertion order), anonymous ones before signed-in ones: opening
            # the login page many times must not sign the household out
            anonymous = next((i for i, s in self._sessions.items() if not s.authenticated), None)
            del self._sessions[anonymous or next(iter(self._sessions))]
