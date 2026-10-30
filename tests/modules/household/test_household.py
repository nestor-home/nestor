"""The household directory: who is behind a sender, on every channel."""

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.household import Account, Household, Person

MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"), Account.parse("voice:*")))
MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde", accounts=(Account.parse("telegram:7"),))


def test_a_sender_is_recognised_on_their_channel_only() -> None:
    household = Household([MATHIS, MATHILDE])
    assert household.identify("telegram", "7") == MATHILDE
    assert household.identify("telegram", "999") is None
    assert household.identify("discord", "7") is None


def test_the_household_lists_its_people() -> None:
    assert Household([MATHIS, MATHILDE]).people == (MATHIS, MATHILDE)
    assert Household([MATHIS]).person(PersonId("mathis")) == MATHIS


def test_a_wildcard_account_stands_for_anyone_on_that_channel() -> None:
    household = Household([MATHIS, MATHILDE])
    assert household.identify("voice", "living-room-mic") == MATHIS


def test_an_account_cannot_belong_to_two_people() -> None:
    twin = Person(id=PersonId("twin"), name="Twin", accounts=(Account.parse("telegram:42"),))
    with pytest.raises(ContractError, match="belongs to both"):
        Household([MATHIS, twin])


def test_an_unknown_person_or_malformed_account_is_a_clear_error() -> None:
    with pytest.raises(ContractError, match="unknown person"):
        Household([MATHIS]).person(PersonId("nobody"))
    with pytest.raises(ContractError, match="channel:sender"):
        Account.parse("telegram")
    assert str(Account.parse("telegram:42")) == "telegram:42"
