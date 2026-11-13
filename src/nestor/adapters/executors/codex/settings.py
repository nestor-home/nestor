"""A Codex executor as the configuration declares it."""

from typing import Any

from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.executors.codex.executor import CodexExecutor
from nestor.adapters.executors.codex.protocol import COMMAND, Sandbox
from nestor.adapters.executors.common import (
    INSTRUCTIONS,
    MAX_FILE_BYTES,
)
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class CodexSettings(AdapterSettings):
    # how to reach `codex app-server`: here, or a relay such as ["ssh", "codex@host", "codex", "app-server", "proxy"]
    command: list[str] = Field(default_factory=lambda: list(COMMAND), min_length=1)
    working_directory: str  # where tasks run, on the machine Codex runs on; files are handed back from there only
    description: str  # what this Codex can really do
    instructions: str = INSTRUCTIONS
    model: str | None = None  # Codex's default when unset
    sandbox: Sandbox = Sandbox.WORKSPACE_WRITE
    config: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})  # per thread
    timeout_s: PositiveFloat = 30.0
    stop_timeout_s: PositiveFloat = 10.0
    max_file_bytes: PositiveInt = MAX_FILE_BYTES


def build(settings: CodexSettings, name: str, services: Services) -> CodexExecutor:
    executor = CodexExecutor(
        settings.command,
        working_directory=settings.working_directory,
        description=settings.description,
        instructions=settings.instructions,
        model=settings.model,
        sandbox=settings.sandbox,
        config=settings.config,
        timeout_s=settings.timeout_s,
        stop_timeout_s=settings.stop_timeout_s,
        max_file_bytes=settings.max_file_bytes,
    )
    executor.name = name  # two Codex setups are two executors
    return executor
