"""The executors and their keys for Nestor's MCP server."""

from datetime import datetime

from pydantic import BaseModel

from nestor.modules.cognition.delegation import Executor, NestorTools


class KeyOut(BaseModel):
    issued_at: datetime
    last_used_at: datetime | None  # the last call it made to Nestor's MCP server


class ExecutorOut(BaseModel):
    name: str
    description: str
    nestor_tools: NestorTools  # how it reaches Nestor's MCP server
    key: KeyOut | None  # None: it has none

    @classmethod
    def of(cls, executor: Executor, keys: dict[str, tuple[datetime, datetime | None]]) -> "ExecutorOut":
        issued = keys.get(executor.name)
        return cls(
            name=executor.name,
            description=executor.description,
            nestor_tools=executor.nestor_tools,
            key=KeyOut(issued_at=issued[0], last_used_at=issued[1]) if issued else None,
        )


class ExecutorsOut(BaseModel):
    url: str | None  # where executors reach Nestor's MCP server; None when they cannot (no public_url, no vault)
    executors: list[ExecutorOut]


class IssuedKeyOut(BaseModel):
    """Shown once: Nestor keeps it only encrypted, to hand to the executors it launches."""

    key: str
    url: str
