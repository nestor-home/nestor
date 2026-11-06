"""What signing in and one's own account take; `MeOut` is shared with accepting an invitation."""

from nestor.admin.api.v1.shared import Input


class LoginIn(Input):
    login: str
    password: str


class LocaleIn(Input):
    locale: str | None  # one of `GET /i18n` locales; None: back to the household's language


class PasswordChangeIn(Input):
    current_password: str
    new_password: str
