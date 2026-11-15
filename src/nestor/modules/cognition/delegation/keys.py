"""The keys executors call Nestor's MCP server with: one per executor, made by Nestor, kept encrypted in the vault.

A key says who calls; the task's capability (`Assignment.task`) says what for: a tool works only with both, and only
while the task runs. A key is shown once when it is made (for an executor configured by hand: Hermes's profile), or
handed by Nestor itself to an executor it launches (`NestorTools.PASSED`). Making one replaces the one before;
revoking leaves the executor without.
"""

import hashlib
import hmac
import secrets
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from nestor.core import Component, ContractError
from nestor.modules.cognition.delegation.events import ExecutorCalled, ExecutorKeyIssued, ExecutorKeyRevoked
from nestor.modules.cognition.delegation.types import NestorAccess
from nestor.modules.journal import Journal

if TYPE_CHECKING:  # connectors import the agent's tools, which import delegation
    from nestor.modules.connectors import CredentialVault

KEY = "nstx_"  # an executor's key
TASK = "nstt_"  # a task's capability
VAULT = "executor:{}"  # the vault's owner of an executor's key
USED_SEEN = 1_000  # the latest calls read back at start, for when each key was last used


def digest(secret: str) -> str:
    """What is kept of a high-entropy secret to recognise it: its SHA-256."""
    return hashlib.sha256(secret.encode()).hexdigest()


def capability() -> str:
    """A new task capability: 32 random bytes."""
    return TASK + secrets.token_urlsafe(32)


class ExecutorKeys(Component):
    name = "executor-keys"

    def __init__(self, journal: Journal, vault: "CredentialVault", url: str, executors: Iterable[str]) -> None:
        """`url`: where executors reach Nestor's MCP server (`admin.public_url` + `/mcp`)."""
        self.journal, self.url = journal, url
        self._vault = vault
        self._executors = tuple(executors)
        self._keys: dict[str, str] = {}  # by executor, decrypted once at start
        self._used: dict[str, datetime] = {}  # when each last called the server

    async def start(self) -> None:
        for executor in self._executors:
            if found := await self._vault.get(VAULT.format(executor), "key"):
                self._keys[executor] = found["key"]
        for call in await self.journal.history(ExecutorCalled, newest_first=True, limit=USED_SEEN):
            self._used.setdefault(call.executor, call.at)

    def used(self, executor: str, at: datetime) -> None:
        """`executor` called the server: what `status` says of its key."""
        self._used[executor] = at

    async def issue(self, executor: str, *, by: str | None = None) -> str:
        """A new key for `executor`, replacing its last; shown once to whoever asked."""
        if executor not in self._executors:
            raise ContractError(f"no executor named {executor!r}")
        key = KEY + secrets.token_urlsafe(32)
        await self._vault.put(VAULT.format(executor), "key", {"key": key})
        self._keys[executor] = key
        await self.journal.publish(ExecutorKeyIssued(source=self.name, executor=executor, by=by))
        return key

    async def revoke(self, executor: str, *, by: str | None = None) -> None:
        if executor not in self._executors:
            raise ContractError(f"no executor named {executor!r}")
        await self._vault.forget(VAULT.format(executor))
        self._keys.pop(executor, None)
        await self.journal.publish(ExecutorKeyRevoked(source=self.name, executor=executor, by=by))

    def caller(self, key: str) -> str | None:
        """The executor whose key this is; every key is compared, in constant time, whatever matches."""
        found = None
        for executor, known in self._keys.items():
            if hmac.compare_digest(known.encode(), key.encode()):
                found = executor
        return found

    async def access(self, executor: str) -> NestorAccess:
        """Where and how `executor` reaches the server, for Nestor to pass it with a task; a key is made the first
        time."""
        key = self._keys.get(executor) or await self.issue(executor)
        return NestorAccess(url=self.url, key=key)

    async def status(self) -> Mapping[str, tuple[datetime, datetime | None]]:
        """By executor with a key: when it was made, and when it was last used since."""
        issued: dict[str, datetime] = {}
        for event in await self.journal.history(ExecutorKeyIssued, ExecutorKeyRevoked):
            if isinstance(event, ExecutorKeyIssued):
                issued[event.executor] = event.at
            else:
                issued.pop(event.executor, None)
        return {
            executor: (at, used if (used := self._used.get(executor)) and used >= at else None)
            for executor, at in issued.items()
        }
