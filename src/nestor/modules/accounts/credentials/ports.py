"""Where verifiers are kept: password hashes and token digests, never the secrets themselves."""

from abc import ABC, abstractmethod

from nestor.core import Component


class VerifierStore(Component, ABC):
    """Verifiers by owner (`account:<id>`, `invitation:<id>`), outside the journal.

    Contract (checked by `nestor.testing.accounts.VerifierStoreContract`): `put` replaces the owner's
    verifier; `get` of an unknown owner is `None`; `forget` removes it and is a no-op when unknown.
    """

    @abstractmethod
    async def put(self, owner: str, verifier: str) -> None: ...

    @abstractmethod
    async def get(self, owner: str) -> str | None: ...

    @abstractmethod
    async def forget(self, owner: str) -> None: ...
