"""Double and contract suite for the account verifier store."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from nestor.modules.accounts import ActivityStore, VerifierStore


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


class InMemoryActivityStore(ActivityStore):
    name = "activity"

    def __init__(self) -> None:
        self.moments: dict[str, datetime] = {}

    async def record(self, account_id: str, at: datetime) -> None:
        self.moments[account_id] = max(at, self.moments.get(account_id, at))

    async def seen(self) -> Mapping[str, datetime]:
        return dict(self.moments)


class ActivityStoreContract:
    """Behaviour every `ActivityStore` must show. Implement `store()`; it is used as a context manager."""

    def store(self) -> ActivityStore:
        raise NotImplementedError

    async def test_the_latest_moment_of_each_account_is_kept(self) -> None:
        earlier = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
        later = earlier + timedelta(hours=1)
        async with self.store() as store:
            await store.record("a", earlier)
            await store.record("a", later)
            await store.record("a", earlier)  # late: never replaces a newer moment
            await store.record("b", earlier)
            assert await store.seen() == {"a": later, "b": earlier}
