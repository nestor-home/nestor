"""OpenAI Codex as a remote executor, through `codex app-server` (JSON-RPC over standard input and output).

A task is a Codex thread, working in the task's own folder under the configured working directory, and each
instruction a turn of it, with an output schema for its report (`common.REPORT_SCHEMA`). The first turn starts the
thread (`thread/start`); a later one goes on in it (`turn/start` on that thread, after `thread/resume` when this
session has not loaded it), so Codex remembers the turns before. Progress comes from the turn's items: what the agent
says and plans, the files it edits, the tools it calls; a command is said without its command line, which may carry a
secret. The outcome comes from the turn once `turn/completed` says it ended, read back with `thread/turns/list`: its
report, or its question for the person; the files the report lists are read back with `fs/readFile`. An instruction
given while a turn works joins it (`turn/steer`, on that turn only). A stop is `turn/interrupt`, confirmed once the
turn reads `interrupted`. The reference is `<thread id>:<turn id>:<folder>`: after a restart, `thread/resume` rejoins
the thread and its turns say how it went. Observed on codex-cli 0.160.0 (2026-11-24).

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
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import Family, Plugin

__all__ = ["CodexExecutor", "CodexSettings", "Sandbox", "build", "plugin"]

plugin = Plugin(
    Family.EXECUTOR,
    "codex",
    CodexSettings,
    build,
    card=Card(
        summary="Hands long tasks to OpenAI's Codex: writes, runs and fixes code in a folder, on this machine or a "
        "server.",
        docs="executors#codex",
        needs=(Need.PROGRAM, Need.ACCOUNT),
    ),
)
