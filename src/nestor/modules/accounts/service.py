"""The account book: accounts and invitations, rebuilt from the journal, changed through it.

Every change is checked against the acting principal's scopes, then written as an event, then applied.
Password hashes and invitation digests go to the verifier store, never into the journal. Changes are
serialised: two acceptances of one invitation, or two owners demoting each other, cannot both pass.
"""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from nestor.core import Component, ContractError, Event, PersonId, new_id, utc_now
from nestor.core.i18n import Locale
from nestor.modules.accounts.credentials import Token, VerifierStore, decoy, hash_password, verify_password
from nestor.modules.accounts.errors import AccountConflict, InvitationRefused, LastOwner, UnknownAccount, WrongPassword
from nestor.modules.accounts.events import (
    AccountCreated,
    AccountDisabled,
    AccountEnabled,
    AccountInvited,
    AccountLocaleChanged,
    AccountLogin,
    AccountPasswordChanged,
    AccountRoleChanged,
    InvitationRevoked,
)
from nestor.modules.accounts.permissions import Principal, Role, Scope
from nestor.modules.accounts.types import Account, Invitation, InvitationStatus, normalise_login
from nestor.modules.household import Household
from nestor.modules.journal import Journal

INVITATION_TTL = timedelta(hours=48)
_PERSONAL = (Role.MEMBER, Role.GUEST)
_REFUSALS = {
    InvitationStatus.ACCEPTED: "this invitation has already been used",
    InvitationStatus.EXPIRED: "this invitation has expired: ask for a new one",
    InvitationStatus.REVOKED: "this invitation was withdrawn",
}


class Accounts(Component):
    name = "accounts"

    def __init__(
        self,
        journal: Journal,
        verifiers: VerifierStore,
        household: Household,
        *,
        invitation_ttl: timedelta = INVITATION_TTL,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal, self.verifiers, self.household = journal, verifiers, household
        self._ttl, self._clock = invitation_ttl, clock
        self.accounts: dict[str, Account] = {}
        self.invitations: dict[str, Invitation] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self.accounts.clear()
        self.invitations.clear()
        for event in await self.journal.history(
            AccountCreated,
            AccountRoleChanged,
            AccountDisabled,
            AccountEnabled,
            AccountLocaleChanged,
            AccountInvited,
            InvitationRevoked,
        ):
            self._apply(event)

    # -- reading ------------------------------------------------------------------------------------

    def get(self, account_id: str) -> Account:
        account = self.accounts.get(account_id)
        if account is None:
            raise UnknownAccount(f"no account {account_id!r}")
        return account

    def by_login(self, login: str) -> Account | None:
        return next((a for a in self.accounts.values() if a.login == login), None)

    def of_person(self, person: PersonId) -> Account | None:
        """The person's active account, if they have one."""
        return next((a for a in self.accounts.values() if a.person == person and not a.disabled), None)

    def listed(self) -> list[Account]:
        return sorted(self.accounts.values(), key=lambda a: a.created_at)

    def owners(self) -> list[Account]:
        return [a for a in self.listed() if a.role is Role.OWNER and not a.disabled]

    def now(self) -> datetime:
        return self._clock()

    # -- signing in -----------------------------------------------------------------------------------

    async def authenticate(self, login: str, password: str, *, client: str = "") -> Account | None:
        """The account these credentials open, or `None`; every attempt is journaled, never the password."""
        try:
            account = self.by_login(normalise_login(login))
        except ContractError:
            account = None
        stored = await self.verifiers.get(_verifier(account.id)) if account else None
        matches = await asyncio.to_thread(verify_password, password, stored or decoy())
        if account is None:
            reason = "unknown-login"
        elif stored is None or not matches:
            reason = "wrong-password"
        elif account.disabled:
            reason = "disabled"
        else:
            reason = ""
        await self.journal.publish(
            AccountLogin(
                source=self.name,
                succeeded=not reason,
                account_id=account.id if account else None,
                client=client,
                reason=reason,
            )
        )
        return None if reason else account

    # -- creating -------------------------------------------------------------------------------------

    async def create(
        self, *, login: str, password: str, role: Role, person: PersonId | None = None, by: Principal | None = None
    ) -> Account:
        """Open an account directly: from the command line (`by=None`), or by someone allowed to grant `role`."""
        if by is not None:
            _may_grant(by, role)
        async with self._lock:
            return await self._create(login, password, role, person, created_by=by.account_id if by else None)

    async def invite(self, role: Role, person: PersonId | None, *, by: Principal) -> tuple[Invitation, Token]:
        """A single-use invitation; the token is returned once and only its digest is kept."""
        _may_grant(by, role)
        async with self._lock:
            self._check_person(role, person)
            token = Token.issue(new_id()[:12])
            await self.verifiers.put(_invitation(token.id), token.digest)
            await self._publish(
                AccountInvited(
                    source=self.name,
                    invitation_id=token.id,
                    role=role,
                    person=person,
                    expires_at=self._clock() + self._ttl,
                    invited_by=by.account_id,
                )
            )
            return self.invitations[token.id], token

    async def invitation(self, token: str) -> Invitation:
        """The pending invitation this token opens; `InvitationRefused` says why it does not."""
        try:
            parsed = Token.parse(token)
        except ContractError:
            raise InvitationRefused("unknown invitation") from None
        invitation = self.invitations.get(parsed.id)
        digest = await self.verifiers.get(_invitation(parsed.id)) if invitation else None
        if invitation is None or (digest is not None and not parsed.matches(digest)):
            raise InvitationRefused("unknown invitation")
        status = invitation.status(self._clock())
        if status is not InvitationStatus.PENDING:
            raise InvitationRefused(_REFUSALS[status])
        if digest is None:  # pending in the journal, but its verifier is gone: never accept it blindly
            raise InvitationRefused("unknown invitation")
        return invitation

    async def accept(self, token: str, *, login: str, password: str) -> Account:
        async with self._lock:
            invitation = await self.invitation(token)
            account = await self._create(
                login,
                password,
                invitation.role,
                invitation.person,
                created_by=invitation.invited_by,
                invitation_id=invitation.id,
            )
            await self.verifiers.forget(_invitation(invitation.id))
            return account

    async def revoke_invitation(self, invitation_id: str, *, by: Principal) -> None:
        by.require(Scope.ACCOUNTS_MANAGE)
        async with self._lock:
            invitation = self.invitations.get(invitation_id)
            if invitation is None:
                raise UnknownAccount(f"no invitation {invitation_id!r}")
            _may_grant(by, invitation.role)
            status = invitation.status(self._clock())
            if status is not InvitationStatus.PENDING:
                raise InvitationRefused(_REFUSALS[status])
            await self._publish(InvitationRevoked(source=self.name, invitation_id=invitation_id, by=by.account_id))
            await self.verifiers.forget(_invitation(invitation_id))

    # -- changing -------------------------------------------------------------------------------------

    async def set_password(
        self, account_id: str, password: str, *, by: Principal | None, current: str | None = None
    ) -> None:
        """One's own password needs the current one; someone else's needs the right to manage that account."""
        account = self.get(account_id)
        if by is not None and by.account_id == account.id:
            stored = await self.verifiers.get(_verifier(account.id))
            if not await asyncio.to_thread(verify_password, current or "", stored or decoy()):
                raise WrongPassword("the current password is wrong")
        elif by is not None:
            _may_touch(by, account)
        encoded = await asyncio.to_thread(hash_password, password)
        async with self._lock:
            await self.verifiers.put(_verifier(account.id), encoded)
            await self._publish(
                AccountPasswordChanged(source=self.name, account_id=account.id, by=by.account_id if by else None)
            )

    async def set_locale(self, account_id: str, locale: Locale | None, *, by: Principal) -> Account:
        """One's own reading language (`None`: the household's); which ones exist is the caller's to check."""
        async with self._lock:
            account = self.get(account_id)
            if by.account_id != account.id:
                _may_touch(by, account)
            if account.locale == locale:
                return account
            await self._publish(AccountLocaleChanged(source=self.name, account_id=account.id, locale=locale))
            return self.accounts[account.id]

    async def change_role(self, account_id: str, role: Role, *, by: Principal) -> Account:
        async with self._lock:
            account = self.get(account_id)
            _may_touch(by, account)
            _may_grant(by, role)
            if account.role is role:
                return account
            if role in _PERSONAL and account.person is None:
                raise ContractError("a member or guest account belongs to a person of the household")
            if account.role is Role.OWNER:
                self._keep_an_owner(account)
            await self._publish(
                AccountRoleChanged(source=self.name, account_id=account.id, role=role, by=by.account_id)
            )
            return self.accounts[account.id]

    async def disable(self, account_id: str, *, by: Principal) -> Account:
        async with self._lock:
            account = self.get(account_id)
            _may_touch(by, account)
            if account.disabled:
                return account
            if account.role is Role.OWNER:
                self._keep_an_owner(account)
            await self._publish(AccountDisabled(source=self.name, account_id=account.id, by=by.account_id))
            return self.accounts[account.id]

    async def enable(self, account_id: str, *, by: Principal) -> Account:
        async with self._lock:
            account = self.get(account_id)
            _may_touch(by, account)
            if not account.disabled:
                return account
            if account.person is not None and self.of_person(account.person) is not None:
                raise AccountConflict("this person already has another active account")
            await self._publish(AccountEnabled(source=self.name, account_id=account.id, by=by.account_id))
            return self.accounts[account.id]

    # -- internals ------------------------------------------------------------------------------------

    async def _create(
        self,
        login: str,
        password: str,
        role: Role,
        person: PersonId | None,
        *,
        created_by: str | None,
        invitation_id: str | None = None,
    ) -> Account:
        login = normalise_login(login)
        if self.by_login(login) is not None:
            raise AccountConflict(f"the login {login!r} is already taken")
        self._check_person(role, person)
        encoded = await asyncio.to_thread(hash_password, password)  # a weak password is refused before anything
        account_id = new_id()[:12]
        # the verifier first: a verifier without its account is harmless, an account without one opens nothing
        await self.verifiers.put(_verifier(account_id), encoded)
        await self._publish(
            AccountCreated(
                source=self.name,
                account_id=account_id,
                login=login,
                role=role,
                person=person,
                invitation_id=invitation_id,
                created_by=created_by,
            )
        )
        return self.accounts[account_id]

    def _check_person(self, role: Role, person: PersonId | None) -> None:
        if person is None:
            if role in _PERSONAL:
                raise ContractError("a member or guest account belongs to a person of the household")
            return
        self.household.person(person)  # ContractError for a stranger
        if self.of_person(person) is not None:
            raise AccountConflict(f"{person} already has an account")

    def _keep_an_owner(self, leaving: Account) -> None:
        if not any(a.id != leaving.id for a in self.owners()):
            raise LastOwner("the household must keep at least one owner: make someone else owner first")

    async def _publish(self, event: Event) -> None:
        await self.journal.publish(event)
        self._apply(event)

    def _apply(self, event: Event) -> None:
        accounts, invitations = self.accounts, self.invitations
        match event:
            case AccountCreated():
                accounts[event.account_id] = Account(
                    id=event.account_id, login=event.login, role=event.role, person=event.person, created_at=event.at
                )
                if event.invitation_id is not None and event.invitation_id in invitations:
                    invitations[event.invitation_id] = replace(
                        invitations[event.invitation_id], accepted_by=event.account_id
                    )
            case AccountRoleChanged() if event.account_id in accounts:
                accounts[event.account_id] = replace(accounts[event.account_id], role=event.role)
            case AccountDisabled() if event.account_id in accounts:
                accounts[event.account_id] = replace(accounts[event.account_id], disabled=True)
            case AccountEnabled() if event.account_id in accounts:
                accounts[event.account_id] = replace(accounts[event.account_id], disabled=False)
            case AccountLocaleChanged() if event.account_id in accounts:
                locale = Locale(event.locale) if event.locale else None
                accounts[event.account_id] = replace(accounts[event.account_id], locale=locale)
            case AccountInvited():
                invitations[event.invitation_id] = Invitation(
                    id=event.invitation_id,
                    role=event.role,
                    person=event.person,
                    invited_by=event.invited_by,
                    created_at=event.at,
                    expires_at=event.expires_at,
                )
            case InvitationRevoked() if event.invitation_id in invitations:
                invitations[event.invitation_id] = replace(invitations[event.invitation_id], revoked=True)


def _may_grant(by: Principal, role: Role) -> None:
    by.require(Scope.ACCOUNTS_MANAGE)
    if role is Role.OWNER:
        by.require(Scope.OWNERS_MANAGE)


def _may_touch(by: Principal, account: Account) -> None:
    by.require(Scope.ACCOUNTS_MANAGE)
    if account.role is Role.OWNER:
        by.require(Scope.OWNERS_MANAGE)


def _verifier(account_id: str) -> str:
    return f"account:{account_id}"


def _invitation(invitation_id: str) -> str:
    return f"invitation:{invitation_id}"
