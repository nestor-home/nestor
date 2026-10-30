"""The household directory: who is who, on every channel."""

from collections.abc import Iterable

from nestor.core import ContractError, PersonId
from nestor.modules.household.types import ANYONE, Person


class Household:
    def __init__(self, people: Iterable[Person]) -> None:
        self._people = {p.id: p for p in people}
        self._accounts: dict[tuple[str, str], Person] = {}
        for person in self._people.values():
            for account in person.accounts:
                key = (account.channel, account.sender)
                if key in self._accounts:
                    other = self._accounts[key].id
                    raise ContractError(f"account {account} belongs to both {other!r} and {person.id!r}")
                self._accounts[key] = person

    @property
    def people(self) -> tuple[Person, ...]:
        return tuple(self._people.values())

    def person(self, person_id: PersonId) -> Person:
        try:
            return self._people[person_id]
        except KeyError:
            raise ContractError(f"unknown person {person_id!r}") from None

    def identify(self, channel: str, sender: str) -> Person | None:
        """The person behind a sender, or `None` for a stranger."""
        return self._accounts.get((channel, sender)) or self._accounts.get((channel, ANYONE))
