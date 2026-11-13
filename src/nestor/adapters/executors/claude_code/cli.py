"""What the `claude` command takes: the command itself, the tools allowed by default, its permission modes."""

from enum import StrEnum

COMMAND = ("claude",)

TOOLS = ("Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "WebFetch")  # its folder and the web, no shell


class PermissionMode(StrEnum):
    DONT_ASK = "dontAsk"  # only what the allowed tools allow
    ACCEPT_EDITS = "acceptEdits"  # file edits in its folder too
    PLAN = "plan"  # reads and plans, changes nothing
    AUTO = "auto"  # Claude Code's classifier decides
    BYPASS = "bypassPermissions"  # everything: for a sandboxed machine only
