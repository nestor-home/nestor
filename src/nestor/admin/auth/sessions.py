"""Admin sessions, kept in memory: a restart logs everyone out, which is acceptable for one household.

The cookie carries a random session id and its HMAC signature; everything else (login state, CSRF
token, pending OAuth flows, messages to show) stays on the server.
"""

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from nestor.core import PersonId


@dataclass(frozen=True, slots=True, kw_only=True)
class Flow:
    """An OAuth authorisation this session started: only this session may complete it."""

    kind: str
    owner: PersonId | None
    replaces: str | None = None  # the broken connection it reconnects, removed once this one works


@dataclass(slots=True, kw_only=True)
class Session:
    id: str
    csrf: str
    expires_at: float
    authenticated: bool = False
    flows: dict[str, Flow] = field(default_factory=dict)  # by OAuth state
    notices: list[str] = field(default_factory=list)  # shown once, on the next page

    def notify(self, text: str) -> None:
        self.notices.append(text)

    def take_notices(self) -> list[str]:
        notices, self.notices = self.notices, []
        return notices


class SessionStore:
    def __init__(self, *, ttl_s: float, limit: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s, self._limit, self._clock = ttl_s, limit, clock
        self._key = secrets.token_bytes(32)
        self._sessions: dict[str, Session] = {}

    def open(self, *, authenticated: bool = False) -> Session:
        self._evict()
        session = Session(
            id=secrets.token_urlsafe(32),
            csrf=secrets.token_urlsafe(32),
            expires_at=self._clock() + self._ttl_s,
            authenticated=authenticated,
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
        if session is None or session.expires_at <= self._clock():
            self._sessions.pop(session_id, None)
            return None
        return session

    def cookie(self, session: Session) -> str:
        return f"{session.id}.{self._sign(session.id)}"

    def close(self, session: Session) -> None:
        self._sessions.pop(session.id, None)

    def _sign(self, session_id: str) -> str:
        return hmac.new(self._key, session_id.encode(), hashlib.sha256).hexdigest()

    def _evict(self) -> None:
        now = self._clock()
        for session_id in [i for i, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[session_id]
        while len(self._sessions) >= self._limit:
            # oldest first (dicts keep insertion order), anonymous ones before logged-in ones: opening
            # the login page many times must not log the household out
            anonymous = next((i for i, s in self._sessions.items() if not s.authenticated), None)
            del self._sessions[anonymous or next(iter(self._sessions))]
