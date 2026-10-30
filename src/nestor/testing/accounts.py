"""Double and contract suite for the account verifier store."""

from nestor.modules.accounts import VerifierStore


class InMemoryVerifierStore(VerifierStore):
    name = "verifiers"

    def __init__(self) -> None:
        self.verifiers: dict[str, str] = {}

    async def put(self, owner: str, verifier: str) -> None:
        self.verifiers[owner] = verifier

    async def get(self, owner: str) -> str | None:
        return self.verifiers.get(owner)

    async def forget(self, owner: str) -> None:
        self.verifiers.pop(owner, None)


class VerifierStoreContract:
    """Behaviour every `VerifierStore` must show. Implement `store()`; it is used as a context manager."""

    def store(self) -> VerifierStore:
        raise NotImplementedError

    async def test_a_verifier_comes_back_until_it_is_replaced_or_forgotten(self) -> None:
        async with self.store() as store:
            await store.put("account:a", "scrypt$first")
            await store.put("account:b", "scrypt$other")
            assert await store.get("account:a") == "scrypt$first"
            await store.put("account:a", "scrypt$second")
            assert await store.get("account:a") == "scrypt$second"
            await store.forget("account:a")
            await store.forget("account:never-stored")
            assert await store.get("account:a") is None
            assert await store.get("account:b") == "scrypt$other"
