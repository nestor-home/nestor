"""Who is acting and what they may do: an account's scopes, or those of the local command line."""

from dataclasses import dataclass

from nestor.core import NestorError, PersonId
from nestor.modules.accounts.permissions.types import Scope


class AccessDenied(NestorError):
    """The acting principal lacks the scope an action needs."""

    def __init__(self, scope: Scope) -> None:
        super().__init__(f"this needs the {scope} permission")
        self.scope = scope


@dataclass(frozen=True, slots=True, kw_only=True)
class Principal:
    scopes: frozenset[Scope]
    person: PersonId | None = None  # whose "own" data the `.own` scopes open
    account_id: str | None = None  # None for the local command line

    def can(self, scope: Scope) -> bool:
        return scope in self.scopes

    def require(self, scope: Scope) -> None:
        if scope not in self.scopes:
            raise AccessDenied(scope)

    def reaches(self, owner: PersonId | None, *, every: Scope, own: Scope, shared: bool = False) -> bool:
        """May act on something belonging to `owner` (`None`: the household as a whole): always with
        `every`; with `own`, only on the principal's person's things — and the household's when `shared`."""
        if every in self.scopes:
            return True
        if own not in self.scopes or self.person is None:
            return False
        return owner == self.person or (shared and owner is None)
