"""The account book: owners from the command line, invitations, roles, the last owner, sign-in attempts."""

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from nestor.core import ContractError, PersonId, utc_now
from nestor.modules.accounts import (
    AccessDenied,
    AccountConflict,
    AccountLogin,
    Accounts,
    InvitationRefused,
    InvitationStatus,
    LastOwner,
    Principal,
    Role,
    UnknownAccount,
    WrongPassword,
)
from nestor.modules.household import Household, Person
from nestor.modules.journal import Journal, LogQuery
from nestor.testing.accounts import InMemoryActivityStore, InMemoryVerifierStore
from nestor.testing.journal import MemoryEventLog

PASSWORD = "correct horse battery"
HOUSEHOLD = Household([Person(id=PersonId(p), name=p.capitalize()) for p in ("mathis", "mathilde", "lucie")])


class Book:
    """An account book on an in-memory journal, with a clock the test moves."""

    def __init__(self) -> None:
        self.log, self.verifiers, self.activity = MemoryEventLog(), InMemoryVerifierStore(), InMemoryActivityStore()
        self.journal = Journal(self.log)
        self.now = utc_now()
        self.accounts = self.reopen()

    def reopen(self) -> Accounts:
        return Accounts(self.journal, self.verifiers, HOUSEHOLD, self.activity, clock=lambda: self.now)

    async def owner(self, login: str = "mathis", person: str | None = "mathis") -> Principal:
        account = await self.accounts.create(
            login=login, password=PASSWORD, role=Role.OWNER, person=PersonId(person) if person else None
        )
        return account.principal()

    async def records(self) -> str:
        return json.dumps([e.record for e in await self.log.read(LogQuery())])


@pytest.fixture
async def book() -> Book:
    book = Book()
    await book.accounts.start()
    return book


async def test_an_owner_from_the_command_line_signs_in_with_any_case_of_their_login(book: Book) -> None:
    await book.owner("Mathis@Example.org")
    account = await book.accounts.authenticate(" MATHIS@example.org ", PASSWORD, client="10.0.0.2")
    assert account is not None and account.role is Role.OWNER and account.person == "mathis"
    (attempt,) = await book.journal.history(AccountLogin)
    assert attempt.succeeded and attempt.account_id == account.id and attempt.client == "10.0.0.2"


@pytest.mark.parametrize(
    ("login", "password", "reason"),
    [
        ("mathis", "wrong password!", "wrong-password"),
        ("nobody", PASSWORD, "unknown-login"),
        ("not a login!", PASSWORD, "unknown-login"),
    ],
)
async def test_a_failed_sign_in_is_journaled_without_the_password(
    book: Book, login: str, password: str, reason: str
) -> None:
    await book.owner()
    assert await book.accounts.authenticate(login, password) is None
    (attempt,) = await book.journal.history(AccountLogin)
    assert not attempt.succeeded and attempt.reason == reason
    assert password not in await book.records() and "scrypt$" not in await book.records()


async def test_a_disabled_account_no_longer_signs_in_until_enabled_again(book: Book) -> None:
    owner = await book.owner()
    member = await book.accounts.create(
        login="mathilde", password=PASSWORD, role=Role.MEMBER, person=PersonId("mathilde")
    )
    await book.accounts.disable(member.id, by=owner)
    assert await book.accounts.authenticate("mathilde", PASSWORD) is None
    assert book.accounts.get(member.id).principal().scopes == frozenset()
    await book.accounts.enable(member.id, by=owner)
    assert await book.accounts.authenticate("mathilde", PASSWORD) is not None


async def test_an_invitation_opens_one_account_with_its_role_and_person(book: Book) -> None:
    owner = await book.owner()
    invitation, token = await book.accounts.invite(Role.MEMBER, PersonId("mathilde"), by=owner)
    assert invitation.expires_at == book.now + timedelta(hours=48)
    assert (await book.accounts.invitation(str(token))).id == invitation.id
    account = await book.accounts.accept(str(token), login="mathilde@free.fr", password=PASSWORD)
    assert (account.role, account.person) == (Role.MEMBER, "mathilde")
    assert await book.accounts.authenticate("mathilde@free.fr", PASSWORD) == account
    assert book.accounts.invitations[invitation.id].status(book.now) is InvitationStatus.ACCEPTED
    with pytest.raises(InvitationRefused, match="already been used"):
        await book.accounts.accept(str(token), login="other", password=PASSWORD)
    assert token.secret not in await book.records() and token.digest not in await book.records()


async def test_an_invitation_expires_after_48_hours(book: Book) -> None:
    owner = await book.owner()
    _, token = await book.accounts.invite(Role.GUEST, PersonId("lucie"), by=owner)
    book.now += timedelta(hours=48)
    with pytest.raises(InvitationRefused, match="expired"):
        await book.accounts.accept(str(token), login="lucie", password=PASSWORD)
    assert book.accounts.by_login("lucie") is None


async def test_a_withdrawn_or_forged_invitation_opens_nothing(book: Book) -> None:
    owner = await book.owner()
    invitation, token = await book.accounts.invite(Role.GUEST, PersonId("lucie"), by=owner)
    for forged in (f"{invitation.id}.{'x' * 43}", "unknown.secret", "garbage"):
        with pytest.raises(InvitationRefused, match="unknown invitation"):
            await book.accounts.invitation(forged)
    await book.accounts.revoke_invitation(invitation.id, by=owner)
    with pytest.raises(InvitationRefused, match="withdrawn"):
        await book.accounts.accept(str(token), login="lucie", password=PASSWORD)
    with pytest.raises(InvitationRefused, match="withdrawn"):
        await book.accounts.revoke_invitation(invitation.id, by=owner)
    with pytest.raises(UnknownAccount):
        await book.accounts.revoke_invitation("nope", by=owner)


async def test_an_invitation_whose_verifier_is_lost_is_never_accepted(book: Book) -> None:
    owner = await book.owner()
    invitation, token = await book.accounts.invite(Role.GUEST, PersonId("lucie"), by=owner)
    await book.verifiers.forget(f"invitation:{invitation.id}")
    with pytest.raises(InvitationRefused, match="unknown invitation"):
        await book.accounts.invitation(str(token))


async def test_two_acceptances_of_one_invitation_open_one_account(book: Book) -> None:
    owner = await book.owner()
    _, token = await book.accounts.invite(Role.MEMBER, PersonId("mathilde"), by=owner)
    results = await asyncio.gather(
        book.accounts.accept(str(token), login="first", password=PASSWORD),
        book.accounts.accept(str(token), login="second", password=PASSWORD),
        return_exceptions=True,
    )
    assert sum(isinstance(r, InvitationRefused) for r in results) == 1
    assert len(book.accounts.listed()) == 2


async def test_only_an_owner_invites_or_promotes_an_owner(book: Book) -> None:
    owner = await book.owner()
    admin = (await book.accounts.create(login="lucie", password=PASSWORD, role=Role.ADMIN, by=owner)).principal()
    with pytest.raises(AccessDenied, match=r"accounts\.owners\.manage"):
        await book.accounts.invite(Role.OWNER, None, by=admin)
    member = await book.accounts.create(
        login="mathilde", password=PASSWORD, role=Role.MEMBER, person=PersonId("mathilde")
    )
    with pytest.raises(AccessDenied):
        await book.accounts.change_role(member.id, Role.OWNER, by=admin)
    owner_id = owner.account_id or ""
    for change in (
        book.accounts.disable(owner_id, by=admin),
        book.accounts.change_role(owner_id, Role.MEMBER, by=admin),
        book.accounts.set_password(owner_id, "a-new-password", by=admin),
    ):
        with pytest.raises(AccessDenied):
            await change
    assert (await book.accounts.change_role(member.id, Role.ADMIN, by=admin)).role is Role.ADMIN
    with pytest.raises(AccessDenied):
        await book.accounts.invite(Role.GUEST, PersonId("lucie"), by=member.principal())


async def test_the_last_owner_can_be_neither_demoted_nor_disabled(book: Book) -> None:
    owner = await book.owner()
    owner_id = owner.account_id or ""
    with pytest.raises(LastOwner):
        await book.accounts.change_role(owner_id, Role.ADMIN, by=owner)
    with pytest.raises(LastOwner):
        await book.accounts.disable(owner_id, by=owner)
    second = await book.accounts.create(
        login="lucie", password=PASSWORD, role=Role.OWNER, person=PersonId("lucie"), by=owner
    )
    assert (await book.accounts.change_role(owner_id, Role.ADMIN, by=second.principal())).role is Role.ADMIN
    with pytest.raises(LastOwner):
        await book.accounts.disable(second.id, by=second.principal())


async def test_members_and_guests_are_people_of_the_household_with_one_account_each(book: Book) -> None:
    owner = await book.owner()
    with pytest.raises(ContractError, match="belongs to a person"):
        await book.accounts.invite(Role.MEMBER, None, by=owner)
    with pytest.raises(ContractError, match="unknown person"):
        await book.accounts.invite(Role.GUEST, PersonId("stranger"), by=owner)
    with pytest.raises(AccountConflict, match="already has an account"):
        await book.accounts.invite(Role.MEMBER, PersonId("mathis"), by=owner)
    with pytest.raises(AccountConflict, match="already taken"):
        await book.accounts.create(login="MATHIS", password=PASSWORD, role=Role.ADMIN)
    technical = await book.accounts.create(login="installer", password=PASSWORD, role=Role.ADMIN, by=owner)
    with pytest.raises(ContractError, match="belongs to a person"):
        await book.accounts.change_role(technical.id, Role.MEMBER, by=owner)
    with pytest.raises(ContractError, match="at least 10"):
        await book.accounts.create(login="lucie", password="short", role=Role.ADMIN)
    assert book.accounts.by_login("lucie") is None


async def test_enabling_an_account_whose_person_has_another_one_is_refused(book: Book) -> None:
    owner = await book.owner()
    old = await book.accounts.create(login="mathilde", password=PASSWORD, role=Role.MEMBER, person=PersonId("mathilde"))
    await book.accounts.disable(old.id, by=owner)
    await book.accounts.create(login="mathilde2", password=PASSWORD, role=Role.MEMBER, person=PersonId("mathilde"))
    with pytest.raises(AccountConflict):
        await book.accounts.enable(old.id, by=owner)


async def test_ones_own_password_needs_the_current_one_and_an_admin_resets_others(book: Book) -> None:
    owner = await book.owner()
    owner_id = owner.account_id or ""
    with pytest.raises(WrongPassword):
        await book.accounts.set_password(owner_id, "brand new password", by=owner, current="not it at all")
    await book.accounts.set_password(owner_id, "brand new password", by=owner, current=PASSWORD)
    assert await book.accounts.authenticate("mathis", "brand new password") is not None
    member = await book.accounts.create(login="lucie", password=PASSWORD, role=Role.MEMBER, person=PersonId("lucie"))
    await book.accounts.set_password(member.id, "reset by the owner", by=owner)
    assert await book.accounts.authenticate("lucie", "reset by the owner") is not None
    assert "reset by the owner" not in await book.records()


async def test_unchanged_roles_and_states_write_nothing(book: Book) -> None:
    owner = await book.owner()
    member = await book.accounts.create(login="lucie", password=PASSWORD, role=Role.MEMBER, person=PersonId("lucie"))
    before = len(await book.log.read(LogQuery()))
    await book.accounts.change_role(member.id, Role.MEMBER, by=owner)
    await book.accounts.enable(member.id, by=owner)
    await book.accounts.disable(member.id, by=owner)
    await book.accounts.disable(member.id, by=owner)
    assert len(await book.log.read(LogQuery())) == before + 1
    with pytest.raises(UnknownAccount):
        book.accounts.get("nope")


async def test_the_book_is_rebuilt_from_the_journal(book: Book) -> None:
    owner = await book.owner()
    member = await book.accounts.create(login="lucie", password=PASSWORD, role=Role.MEMBER, person=PersonId("lucie"))
    await book.accounts.change_role(member.id, Role.ADMIN, by=owner)
    await book.accounts.disable(member.id, by=owner)
    accepted, token = await book.accounts.invite(Role.MEMBER, PersonId("mathilde"), by=owner)
    await book.accounts.accept(str(token), login="mathilde", password=PASSWORD)
    pending, _ = await book.accounts.invite(Role.ADMIN, None, by=owner)
    await book.accounts.revoke_invitation(pending.id, by=owner)

    reopened = book.reopen()
    await reopened.start()
    assert reopened.accounts == book.accounts.accounts
    assert reopened.invitations == book.accounts.invitations
    assert reopened.invitations[accepted.id].status(book.now) is InvitationStatus.ACCEPTED
    assert reopened.invitations[pending.id].status(book.now) is InvitationStatus.REVOKED
    assert [a.login for a in reopened.owners()] == ["mathis"]


def test_an_invitation_status_follows_time() -> None:
    from nestor.modules.accounts import Invitation

    now = datetime(2026, 10, 30, 12, 0)
    invitation = Invitation(
        id="i", role=Role.GUEST, person=None, invited_by=None, created_at=now, expires_at=now + timedelta(hours=1)
    )
    assert invitation.status(now) is InvitationStatus.PENDING
    assert invitation.status(now + timedelta(hours=1)) is InvitationStatus.EXPIRED


async def test_a_reading_language_is_ones_own_choice_or_an_administrators(book: Book) -> None:
    from nestor.core.i18n import Locale

    owner = await book.owner()
    member = await book.accounts.create(login="lucie", password=PASSWORD, role=Role.MEMBER, person=PersonId("lucie"))
    chosen = await book.accounts.set_locale(member.id, Locale("en"), by=member.principal())
    assert chosen.locale == "en"
    before = len(await book.log.read(LogQuery()))
    await book.accounts.set_locale(member.id, Locale("en"), by=owner)
    assert len(await book.log.read(LogQuery())) == before, "unchanged: nothing written"
    other = await book.accounts.create(
        login="mathilde", password=PASSWORD, role=Role.MEMBER, person=PersonId("mathilde")
    )
    with pytest.raises(AccessDenied):
        await book.accounts.set_locale(other.id, Locale("en"), by=member.principal())
    reopened = book.reopen()
    await reopened.start()
    assert reopened.get(member.id).locale == "en"
    await book.accounts.set_locale(member.id, None, by=member.principal())
    assert book.accounts.get(member.id).locale is None


async def test_an_account_is_seen_at_each_sign_in_and_written_at_most_once_a_minute(book: Book) -> None:
    owner = await book.owner()
    assert book.accounts.last_seen(owner.account_id or "") is None
    signed_in = book.now
    await book.accounts.authenticate("mathis", PASSWORD)
    book.now += timedelta(seconds=30)
    await book.accounts.touch(owner.account_id or "")
    assert book.accounts.last_seen(owner.account_id or "") == book.now
    assert await book.activity.seen() == {owner.account_id: signed_in}, "not written again within the minute"
    book.now += timedelta(seconds=31)
    await book.accounts.touch(owner.account_id or "")
    reopened = book.reopen()
    await reopened.start()
    assert reopened.last_seen(owner.account_id or "") == book.now
