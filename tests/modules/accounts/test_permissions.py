"""Roles grant scopes in one table; a principal reaches its own person's things, or everyone's."""

import pytest

from nestor.core import PersonId
from nestor.modules.accounts import GRANTS, AccessDenied, Principal, Role, Scope

MATHILDE = PersonId("mathilde")


def test_the_owner_holds_every_scope_and_each_role_holds_less_than_the_one_above() -> None:
    assert GRANTS[Role.OWNER] == frozenset(Scope)
    assert GRANTS[Role.GUEST] < GRANTS[Role.MEMBER] < GRANTS[Role.ADMIN] < GRANTS[Role.OWNER]
    assert Scope.OWNERS_MANAGE not in GRANTS[Role.ADMIN], "only owners touch owners"


@pytest.mark.parametrize(
    ("role", "scope"),
    [
        (Role.MEMBER, Scope.JOURNAL_READ_ALL),
        (Role.MEMBER, Scope.ACCOUNTS_MANAGE),
        (Role.MEMBER, Scope.SATELLITES_MANAGE),
        (Role.GUEST, Scope.HOUSEHOLD_READ),
        (Role.GUEST, Scope.OWN_CONNECTIONS),
    ],
)
def test_a_missing_scope_is_refused_by_name(role: Role, scope: Scope) -> None:
    principal = Principal(scopes=GRANTS[role], person=MATHILDE)
    with pytest.raises(AccessDenied, match=scope.value):
        principal.require(scope)


def test_own_scopes_reach_the_principals_person_only_and_shared_things_when_asked() -> None:
    member = Principal(scopes=GRANTS[Role.MEMBER], person=MATHILDE)
    every, own = Scope.MEMORY_MANAGE_ALL, Scope.MEMORY_MANAGE_OWN
    assert member.reaches(MATHILDE, every=every, own=own)
    assert not member.reaches(PersonId("mathis"), every=every, own=own)
    assert not member.reaches(None, every=every, own=own)
    assert member.reaches(None, every=every, own=own, shared=True)
    assert Principal(scopes=GRANTS[Role.ADMIN]).reaches(PersonId("mathis"), every=every, own=own)
    assert not Principal(scopes=GRANTS[Role.MEMBER]).reaches(None, every=every, own=own, shared=True)
