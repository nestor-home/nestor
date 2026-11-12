"""The household directory: who is behind a sender, on every channel."""

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Sender
from nestor.modules.household import Account, Household, Person

MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),))
MATHILDE = Person(id=PersonId("mathilde"), name="Mathilde", accounts=(Account.parse("telegram:7"),))


def test_a_sender_is_recognised_on_their_channel_only() -> None:
    household = Household([MATHIS, MATHILDE])
    assert household.identify("telegram", Sender("7")) == MATHILDE
    assert household.identify("telegram", Sender("999")) is None
    assert household.identify("discord", Sender("7")) is None


def test_a_channel_that_signs_people_in_names_them_without_an_account() -> None:
    """The admin's chat: its session vouches for the person, who needs no account on it."""
    household = Household([MATHIS, MATHILDE])
    assert household.identify("web", Sender("session", person=PersonId("mathilde"))) == MATHILDE
    assert household.identify("web", Sender("session", person=PersonId("gone"))) is None


def test_an_account_stands_for_one_person_not_anyone() -> None:
    """A shared device is a place, not an account: who speaks there is told by their voice or their words."""
    with pytest.raises(ContractError, match="not anyone"):
        Account.parse("satellites:*")


def test_an_account_cannot_belong_to_two_people() -> None:
    twin = Person(id=PersonId("twin"), name="Twin", accounts=(Account.parse("telegram:42"),))
    with pytest.raises(ContractError, match="belongs to both"):
        Household([MATHIS, twin])


def test_an_unknown_person_or_malformed_account_is_a_clear_error() -> None:
    assert Household([MATHIS]).person(PersonId("mathis")) == MATHIS
    with pytest.raises(ContractError, match="unknown person"):
        Household([MATHIS]).person(PersonId("nobody"))
    with pytest.raises(ContractError, match="channel:sender"):
        Account.parse("telegram")
    assert str(Account.parse("telegram:42")) == "telegram:42"
