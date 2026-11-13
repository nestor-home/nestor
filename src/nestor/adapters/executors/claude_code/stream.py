"""Claude Code's `stream-json` output as Nestor reads it: the steps of the work and the report."""

from collections.abc import Mapping
from typing import Any

from nestor.adapters.executors.common import step

REPORTING = "StructuredOutput"  # the tool it ends with to give its report: not a step of the work

SHOWN_INPUT = ("command", "file_path", "path", "pattern", "query", "url", "description")  # what a step names


def tool_step(used: Mapping[str, Any]) -> str:
    given: Mapping[str, Any] = used["input"] if isinstance(used.get("input"), dict) else {}
    shown = next((str(given[key]) for key in SHOWN_INPUT if given.get(key)), None)
    return step(f"{used.get('name')}: {shown}" if shown else str(used.get("name")))
