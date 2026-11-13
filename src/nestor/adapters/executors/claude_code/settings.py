"""A Claude Code executor as the configuration declares it."""

from pathlib import Path

from pydantic import Field, PositiveFloat, PositiveInt, SecretStr

from nestor.adapters.executors.claude_code.cli import COMMAND, TOOLS, PermissionMode
from nestor.adapters.executors.claude_code.executor import ClaudeCodeExecutor
from nestor.adapters.executors.common import (
    INSTRUCTIONS,
    MAX_FILE_BYTES,
)
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class ClaudeCodeSettings(AdapterSettings):
    command: list[str] = Field(default_factory=lambda: list(COMMAND), min_length=1)  # the `claude` command
    working_directory: Path  # where tasks run; files are handed back from there only
    description: str  # what this Claude Code can really do
    instructions: str = INSTRUCTIONS
    model: str | None = None  # Claude Code's default when unset
    permission_mode: PermissionMode = PermissionMode.DONT_ASK
    allowed_tools: list[str] = Field(default_factory=lambda: list(TOOLS))  # e.g. "Bash(git *)"
    disallowed_tools: list[str] = Field(default_factory=list)
    max_budget_usd: PositiveFloat | None = None  # per task
    api_key: SecretStr | None = None  # without it, the account Claude Code is signed in with
    stop_timeout_s: PositiveFloat = 10.0
    max_file_bytes: PositiveInt = MAX_FILE_BYTES


def build(settings: ClaudeCodeSettings, name: str, services: Services) -> ClaudeCodeExecutor:
    executor = ClaudeCodeExecutor(
        settings.command,
        working_directory=settings.working_directory,
        description=settings.description,
        instructions=settings.instructions,
        model=settings.model,
        permission_mode=settings.permission_mode,
        allowed_tools=settings.allowed_tools,
        disallowed_tools=settings.disallowed_tools,
        max_budget_usd=settings.max_budget_usd,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        stop_timeout_s=settings.stop_timeout_s,
        max_file_bytes=settings.max_file_bytes,
    )
    executor.name = name  # two Claude Code setups are two executors
    return executor
