"""OpenAI Codex as a remote executor, through `codex app-server` (JSON-RPC over standard input and output).

A task is a thread started in the configured working directory and one turn carrying the objective, with an
output schema for the final report (`common.REPORT_SCHEMA`). Progress comes from the turn's `item/started`
notifications; the outcome from the turn once `turn/completed` says it ended, read back with `thread/turns/list`;
the files the report lists are read back with `fs/readFile`. A stop is `turn/interrupt`, confirmed once the turn
reads `interrupted`. The reference is `<thread id>:<turn id>`: after a restart, `thread/resume` rejoins the thread
and its turns say how it went. Observed on codex-cli 0.160.0 (2026-11-13).

Codex runs where the command runs: `codex app-server` here, or behind a relay to a Codex daemon elsewhere
(`ssh codex@host codex app-server proxy`), whose turns outlive Nestor. A local `codex app-server` stops with
Nestor: the turn it ran is then reported as cut short.

Approvals: Codex never waits for one (`approvalPolicy: never`). What it may do is its sandbox: `read-only`,
`workspace-write` (the working directory, no network unless its configuration allows it) or `danger-full-access`.
A request for an approval or for input that still comes is declined: nobody answers for the household there.
"""

from nestor.adapters.executors.codex.executor import CodexExecutor
from nestor.adapters.executors.codex.protocol import Sandbox
from nestor.adapters.executors.codex.settings import CodexSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["CodexExecutor", "CodexSettings", "Sandbox", "build", "plugin"]

plugin = Plugin(Family.EXECUTOR, "codex", CodexSettings, build)
