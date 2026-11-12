"""The household directory: who is who, on every channel."""

from collections.abc import Iterable

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Sender
from nestor.modules.household.types import Account, Person


class SharedAccount(ContractError):
    """Two people claim the same account: a channel could not tell who is writing or speaking."""

    def __init__(self, account: Account, first: PersonId, second: PersonId) -> None:
        super().__init__(f"account {account} belongs to both {first!r} and {second!r}")
        self.account = account


class Household:
    def __init__(self, people: Iterable[Person]) -> None:
        self._people = {p.id: p for p in people}
        self._accounts: dict[tuple[str, str], Person] = {}
        for person in self._people.values():
            for account in person.accounts:
                key = (account.channel, account.sender)
                if key in self._accounts:
                    raise SharedAccount(account, self._accounts[key].id, person.id)
                self._accounts[key] = person

    @property
    def people(self) -> tuple[Person, ...]:
        return tuple(self._people.values())

    def person(self, person_id: PersonId) -> Person:
        try:
            return self._people[person_id]
        except KeyError:
            raise ContractError(f"unknown person {person_id!r}") from None

    def name_of(self, person_id: PersonId | None, default: str) -> str:
        """The person's name, or `default` for nobody known."""
        found = self._people.get(person_id) if person_id is not None else None
        return found.name if found else default

    def identify(self, channel: str, sender: Sender) -> Person | None:
        """The person behind a sender: the one the channel signed in and names, else the owner of the account;
        `None` for a stranger."""
        if sender.person is not None:
            return self._people.get(sender.person)
        return self._accounts.get((channel, sender.id))
