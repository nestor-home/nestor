"""Which language a request is answered in: the signed-in account's choice, else the household's
for a signed-in account, else the browser's `Accept-Language` when anonymous (negotiated against the
catalogues), else the household's."""

from fastapi import Request

from nestor.admin.state import AdminState, state
from nestor.core.i18n import Locale, negotiate
from nestor.modules.accounts import Account

_NONE = Locale("")


def household_locale(admin: AdminState) -> Locale:
    localizer = admin.nestor.localizer
    return negotiate(admin.nestor.config.persona.locale, localizer.locales, localizer.default)


def account_locale(admin: AdminState, account: Account) -> Locale:
    if account.locale is None:
        return household_locale(admin)
    localizer = admin.nestor.localizer
    return negotiate(account.locale, localizer.locales, household_locale(admin))


def accepted(admin: AdminState, header: str) -> Locale:
    """The first language of `Accept-Language` (by weight) a catalogue has; the household's otherwise."""
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        weight = 1.0
        if params.strip().startswith("q="):
            try:
                weight = float(params.strip()[2:])
            except ValueError:
                weight = 0.0
        if tag and tag != "*" and weight > 0:
            ranked.append((-weight, index, tag))
    for _, _, tag in sorted(ranked):
        found = negotiate(tag, admin.nestor.localizer.locales, _NONE)
        if found != _NONE:
            return found
    return household_locale(admin)


def reader_locale(request: Request) -> Locale:
    admin = state(request)
    session = admin.cookie.read(request)
    account = admin.accounts.accounts.get(session.account_id or "") if session else None
    if account is not None and not account.disabled:
        return account_locale(admin, account)
    return accepted(admin, request.headers.get("accept-language", ""))
