"""The session cookie: HttpOnly, SameSite=Strict, Secure when the admin is served over HTTPS."""

from fastapi import Request, Response

from nestor.admin.auth.sessions import Session, SessionStore

COOKIE = "nestor_session"


class SessionCookie:
    def __init__(self, sessions: SessionStore) -> None:
        self.sessions = sessions

    def read(self, request: Request) -> Session | None:
        return self.sessions.find(request.cookies.get(COOKIE))

    def give(self, response: Response, session: Session, *, secure: bool) -> None:
        response.set_cookie(
            COOKIE,
            self.sessions.cookie(session),
            max_age=int(self.sessions.ttl_s),
            httponly=True,
            samesite="strict",
            secure=secure,
            path="/",
        )

    @staticmethod
    def clear(response: Response) -> None:
        response.delete_cookie(COOKIE, path="/")
