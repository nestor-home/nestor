"""What signing in and one's own account take; `MeOut` is shared with accepting an invitation."""

from pydantic import BaseModel

from nestor.admin.api.v1.accounts.schemas import AccountOut
from nestor.admin.api.v1.agent.schemas import AgentOut
from nestor.admin.api.v1.language import account_locale
from nestor.admin.api.v1.shared import Input, People
from nestor.admin.auth import Session
from nestor.admin.state import AdminState
from nestor.modules.accounts import Account, Scope


class LoginIn(Input):
    login: str
    password: str


class LocaleIn(Input):
    locale: str | None  # one of `GET /i18n` locales; None: back to the household's language


class PasswordChangeIn(Input):
    current_password: str
    new_password: str


class MeOut(BaseModel):
    account: AccountOut
    locale: str  # the language it reads in: its choice, else the household's (`account.locale` is the choice)
    scopes: list[Scope]  # what the front may offer; the API checks them again on every request
    csrf_token: str  # send it back in `X-CSRF-Token` on every POST, PUT, PATCH and DELETE
    assistant: str  # the assistant's name, for the front's header (also `agent.name`)
    agent: AgentOut
    restart_required: bool  # the configuration was written since the instance started
    pending_changes: list[str]

    @classmethod
    def of(cls, admin: AdminState, account: Account, session: Session) -> "MeOut":
        return cls(
            account=AccountOut.of(account, People(admin.nestor.household), admin.accounts),
            locale=account_locale(admin, account),
            scopes=sorted(account.principal().scopes),
            csrf_token=session.csrf,
            assistant=admin.nestor.config.persona.name,
            agent=AgentOut.of(admin.nestor),
            restart_required=bool(admin.pending_changes),
            pending_changes=admin.pending_changes,
        )
