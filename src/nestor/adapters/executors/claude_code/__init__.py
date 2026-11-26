"""Anthropic's Claude Code as an executor, run headless: `claude -p --input-format stream-json --output-format
stream-json`.

A task is one Claude Code session, in the task's own folder under the configured working directory. Its first turn
chooses the session's id (`--session-id`), journaled as the first step: a person can open it again with
`claude --resume <id>`; each later turn goes on in it (`--resume <id>`, same folder). The instruction goes in on
standard input as a user message; another message written there while the turn works is read between two of its
steps (steering). The turn's first `result` message ends it: its input is closed, and the process exits once it has
answered what it was sent (an instruction that arrived just as the turn ended gets a turn, and a result, of its own:
their reports are joined). The report comes back structured (`--json-schema`, `common.REPORT_SCHEMA`), a question
for the person included, and the files it lists are read from the task's folder. Progress comes from the tool calls
of the stream, named by what they act on, never by a shell command. Observed on Claude Code 2.1.323 (2026-11-24).

A turn runs in a child process of Nestor: it stops with Nestor, and the turn is then reported as interrupted
(Claude Code is an `Executor`, not a `RemoteExecutor`). A stop ends its process group, killed if it does not
stop when asked, and is confirmed once the process has exited.

Permissions: nobody answers a prompt in a headless run. `permission_mode` and the allowed and disallowed tools
decide what runs (Claude Code's own rules: `dontAsk` denies whatever they do not allow); `max_budget_usd` caps
what one turn may spend. The official Agent SDK for Python is not used: it bundles its own copy of the command
(150 MB a platform) and speaks the same stream.
"""

from nestor.adapters.executors.claude_code.cli import PermissionMode
from nestor.adapters.executors.claude_code.executor import ClaudeCodeExecutor
from nestor.adapters.executors.claude_code.settings import ClaudeCodeSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["ClaudeCodeExecutor", "ClaudeCodeSettings", "PermissionMode", "build", "plugin"]

plugin = Plugin(Family.EXECUTOR, "claude-code", ClaudeCodeSettings, build)
