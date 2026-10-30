"""Secrets of the configuration, kept in the encrypted vault and named in the YAML as `${secret:name}`.

The file never holds them: the admin and `nestor secrets` write the vault, the YAML only refers to
them, and loading the configuration resolves the references. A value is never logged nor journaled.
"""

import contextlib
import re
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

import yaml

from nestor.adapters.storage.sqlite import SealedReader
from nestor.core import ContractError
from nestor.modules.connectors import CredentialVault
from nestor.modules.journal import Journal
from nestor.modules.system import SecretChanged
from nestor.runtime.config import SECRET_KEY, SecretLookup, references, substitute

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,99}$")
_INDEX = ("config", "index")  # the names of the secrets set, so they can be listed


def _owner(name: str) -> str:
    return f"config:{name}"


def preview(value: str) -> str:
    """Enough to recognise a value, never enough to use it: `sk-…4f2`."""
    return f"{value[:3]}…{value[-3:]}" if len(value) >= 12 else "•" * 3


def vault_reader(data_dir: Path, key: str) -> SecretLookup:
    from nestor.runtime.app import database_path

    reader = SealedReader(database_path(data_dir), key)

    def lookup(name: str) -> str | None:
        found = reader.get(_owner(name), "value")
        return found["value"] if found else None

    return lookup


class ConfigSecrets:
    """The configuration's secrets in a vault, each change journaled without its value."""

    def __init__(self, vault: CredentialVault, journal: Journal) -> None:
        self.vault, self.journal = vault, journal

    async def names(self) -> list[str]:
        index = await self.vault.get(*_INDEX) or {}
        return sorted(index)

    async def value(self, name: str) -> str | None:
        found = await self.vault.get(_owner(name), "value")
        return found["value"] if found else None

    async def set(self, name: str, value: str, *, by: str) -> None:
        if not NAME.match(name):
            raise ContractError("a secret name is letters, digits, `_`, `.` and `-`, starting with a letter")
        if not value:
            raise ContractError("a secret cannot be empty: delete it instead")
        await self.vault.put(_owner(name), "value", {"value": value})
        index = dict(await self.vault.get(*_INDEX) or {})
        await self.vault.put(*_INDEX, {**index, name: "1"})
        await self.journal.publish(SecretChanged(source="config", name=name, by=by))

    async def delete(self, name: str, *, by: str) -> bool:
        """Forget it; `False` when there was nothing to forget."""
        index = dict(await self.vault.get(*_INDEX) or {})
        if name not in index:
            return False
        del index[name]
        await self.vault.forget(_owner(name))
        await self.vault.put(*_INDEX, index)
        await self.journal.publish(SecretChanged(source="config", name=name, by=by, removed=True))
        return True


class ConfigFile:
    """A configuration file read as plain data, without resolving it: where its data lives, and which
    secrets it refers to (what `nestor secrets` needs, even while a secret is missing)."""

    def __init__(self, path: Path, environ: Mapping[str, str]) -> None:
        self.path, self.environ = path, environ
        try:
            raw = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as error:
            raise ContractError(f"cannot read {path}: {error}") from None
        self.raw: dict[str, Any] = raw if isinstance(raw, dict) else {}

    @property
    def data_dir(self) -> Path:
        return Path(str(substitute(self.raw.get("data_dir", "data"), dict(self.environ), lambda name: None)))

    def used(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for path, name, secret in references(self.raw):
            if secret:
                found.setdefault(name, []).append(".".join(str(p) for p in path))
        return found


@contextlib.asynccontextmanager
async def open_secrets(data_dir: Path, key: str | None) -> AsyncGenerator[ConfigSecrets]:
    """The configuration's secrets in the vault of `data_dir`, without the rest of Nestor."""
    from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEventLog, SQLiteVault
    from nestor.runtime.app import database_path

    if not key:
        raise ContractError(f"{SECRET_KEY} is not set: the vault cannot be opened without it")
    database = SQLiteDatabase(database_path(data_dir))
    async with database:
        yield ConfigSecrets(SQLiteVault(database, key), Journal(SQLiteEventLog(database)))
