"""The SQLite vault: connector secrets sealed at rest, opened only with the instance key."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteVault
from nestor.core import ContractError
from nestor.modules.connectors import CredentialVault
from nestor.testing.connectors import CredentialVaultContract

KEY = "k" * 40


class TestSQLiteVault(CredentialVaultContract):
    @pytest.fixture(autouse=True)
    def _directory(self, tmp_path: Path) -> None:
        self.path = tmp_path / "nestor.db"

    def vault(self) -> CredentialVault:
        return SQLiteVault(SQLiteDatabase(self.path), KEY, owns_database=True)

    def stored_bytes(self) -> bytes:
        return b"".join(p.read_bytes() for p in self.path.parent.glob("nestor.db*"))


async def test_secrets_survive_a_restart_with_the_same_key(tmp_path: Path) -> None:
    async with SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), KEY, owns_database=True) as vault:
        await vault.put("c1", "tokens", {"access_token": "a"})
    async with SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), KEY, owns_database=True) as vault:
        assert await vault.get("c1", "tokens") == {"access_token": "a"}


async def test_another_key_cannot_open_them_and_says_why(tmp_path: Path) -> None:
    async with SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), KEY, owns_database=True) as vault:
        await vault.put("c1", "tokens", {"access_token": "a"})
    async with SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), "x" * 40, owns_database=True) as vault:
        with pytest.raises(ContractError, match="NESTOR_SECRET_KEY changed"):
            await vault.get("c1", "tokens")


async def test_a_sealed_value_moved_to_another_owner_does_not_open(tmp_path: Path) -> None:
    async with SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), KEY, owns_database=True) as vault:
        await vault.put("victim", "tokens", {"access_token": "a"})
        await vault.put("attacker", "tokens", {"access_token": "b"})
        await vault.database.write(
            lambda c: c.execute(
                "UPDATE secrets SET sealed = (SELECT sealed FROM secrets WHERE owner = 'victim') "
                "WHERE owner = 'attacker'"
            )
        )
        with pytest.raises(ContractError, match="cannot be opened"):
            await vault.get("attacker", "tokens")


def test_a_short_secret_is_refused_with_how_to_generate_one(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match=r"secrets\.token_urlsafe"):
        SQLiteVault(SQLiteDatabase(tmp_path / "n.db"), "short")
