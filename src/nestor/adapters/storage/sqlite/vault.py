"""Connector secrets in SQLite, sealed with AES-256-GCM.

The key is derived (HKDF-SHA256) from the instance secret the runtime reads from `NESTOR_SECRET_KEY`:
losing it makes every stored token unreadable, which only means connecting the accounts again. Each
row is bound to its `(owner, name)` as associated data, so a sealed value moved to another row does
not open.
"""

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.adapters.storage.sqlite.event_log import time_key
from nestor.core import ContractError, utc_now
from nestor.modules.connectors import CredentialVault, Secrets

MIN_SECRET_LENGTH = 32
GENERATE = "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
_NONCE = 12


class SQLiteVault(CredentialVault):
    name = "sqlite-vault"

    def __init__(self, database: SQLiteDatabase, secret: str, *, owns_database: bool = False) -> None:
        if len(secret) < MIN_SECRET_LENGTH:
            raise ContractError(
                f"the vault secret must be at least {MIN_SECRET_LENGTH} characters: generate one with {GENERATE}"
            )
        self.database = database
        self._owns_database = owns_database
        self._cipher = _cipher(secret)

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def put(self, owner: str, name: str, secrets: Secrets) -> None:
        nonce = os.urandom(_NONCE)
        plain = json.dumps(dict(secrets), ensure_ascii=False).encode()
        sealed = nonce + self._cipher.encrypt(nonce, plain, _bound(owner, name))
        row = (owner, name, sealed, time_key(utc_now()))
        await self.database.write(
            lambda c: c.execute(
                "INSERT INTO secrets (owner, name, sealed, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (owner, name) DO UPDATE SET sealed = excluded.sealed, updated_at = excluded.updated_at",
                row,
            )
        )

    async def get(self, owner: str, name: str) -> Secrets | None:
        def query(connection: sqlite3.Connection) -> tuple[bytes] | None:
            return connection.execute(
                "SELECT sealed FROM secrets WHERE owner = ? AND name = ?", (owner, name)
            ).fetchone()

        row = await self.database.read(query)
        if row is None:
            return None
        return _open(self._cipher, row[0], owner, name)

    async def forget(self, owner: str) -> None:
        await self.database.write(lambda c: c.execute("DELETE FROM secrets WHERE owner = ?", (owner,)))


class SealedReader:
    """Reads the vault without the event loop, before Nestor starts (resolving `${secret:…}` while the
    configuration loads). WAL lets it read while a running instance writes."""

    def __init__(self, path: Path, secret: str) -> None:
        if len(secret) < MIN_SECRET_LENGTH:
            raise ContractError(f"the vault secret must be at least {MIN_SECRET_LENGTH} characters")
        self.path, self._cipher = path, _cipher(secret)

    def get(self, owner: str, name: str) -> Secrets | None:
        if not self.path.exists():
            return None
        with contextlib.closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as connection:
            try:
                row = connection.execute(
                    "SELECT sealed FROM secrets WHERE owner = ? AND name = ?", (owner, name)
                ).fetchone()
            except sqlite3.OperationalError:  # a database the migrations have not reached yet
                return None
        return _open(self._cipher, row[0], owner, name) if row else None


def _cipher(secret: str) -> AESGCM:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"nestor credential vault v1")
    return AESGCM(key.derive(secret.encode()))


def _open(cipher: AESGCM, sealed: bytes, owner: str, name: str) -> Secrets:
    try:
        plain = cipher.decrypt(sealed[:_NONCE], sealed[_NONCE:], _bound(owner, name))
    except InvalidTag:
        raise ContractError(
            f"secret {name!r} of {owner!r} cannot be opened: NESTOR_SECRET_KEY changed since it was stored"
        ) from None
    return {str(k): str(v) for k, v in json.loads(plain).items()}


def _bound(owner: str, name: str) -> bytes:
    return json.dumps([owner, name]).encode()
