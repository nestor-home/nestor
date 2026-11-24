"""Tools: short, frequent actions the central agent calls directly (home, memory, tasks…).

A tool answers in about a second; one slower than the turn waits for goes on in the background and its result comes
back to the conversation. Long work belongs to an executor.
"""

from nestor.modules.cognition.tools.events import ResultStored, ToolCalled, ToolCompleted, ToolDeferred, ToolReturned
from nestor.modules.cognition.tools.ports import InWriting, ToolProvider
from nestor.modules.cognition.tools.results import Results
from nestor.modules.cognition.tools.service import Called, Toolbox
from nestor.modules.cognition.tools.types import (
    TITLE,
    TITLE_CHARS,
    Made,
    Risk,
    SensitiveWhen,
    Tool,
    ToolContext,
    ToolFailed,
    ToolOutput,
    bounded,
    titled,
)

__all__ = [
    "TITLE",
    "TITLE_CHARS",
    "Called",
    "InWriting",
    "Made",
    "ResultStored",
    "Results",
    "Risk",
    "SensitiveWhen",
    "Tool",
    "ToolCalled",
    "ToolCompleted",
    "ToolContext",
    "ToolDeferred",
    "ToolFailed",
    "ToolOutput",
    "ToolProvider",
    "ToolReturned",
    "Toolbox",
    "bounded",
    "titled",
]
