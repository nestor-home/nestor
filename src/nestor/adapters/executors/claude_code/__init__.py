"""Anthropic's Claude Code as an executor, run headless: `claude -p --output-format stream-json`.

A task is one session in the configured working directory, its id chosen by Nestor (`--session-id`) and journaled as
the first step: a person can open it again with `claude --resume <id>`. The objective goes in on standard input, the
final report comes back structured (`--json-schema`, `common.REPORT_SCHEMA`), and the files it lists are read from
the working directory. Progress comes from the tool calls of the stream. Observed on Claude Code 2.1.311
(2026-11-13).

The session runs in a child process of Nestor: it stops with Nestor, and the task is then reported as interrupted
(Claude Code is an `Executor`, not a `RemoteExecutor`). A stop ends its process group, killed if it does not
stop when asked, and is confirmed once the process has exited.

Permissions: nobody answers a prompt in a headless run. `permission_mode` and the allowed and disallowed tools
decide what runs (Claude Code's own rules: `dontAsk` denies whatever they do not allow); `max_budget_usd` caps
what one task may spend. The official Agent SDK for Python is not used: it bundles its own copy of the command
(150 MB a platform) and speaks the same stream.
"""

from nestor.adapters.executors.claude_code.cli import PermissionMode
from nestor.adapters.executors.claude_code.executor import ClaudeCodeExecutor
from nestor.adapters.executors.claude_code.settings import ClaudeCodeSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["ClaudeCodeExecutor", "ClaudeCodeSettings", "PermissionMode", "build", "plugin"]

plugin = Plugin(Family.EXECUTOR, "claude-code", ClaudeCodeSettings, build)
