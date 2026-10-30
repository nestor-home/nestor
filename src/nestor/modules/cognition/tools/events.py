"""Events of tool calls: what the agent did, with which arguments, and what came back."""

from collections.abc import Mapping

from nestor.core import Event, PersonId
from nestor.modules.channels import Address


class ToolCalled(Event, event_type="agent.tool.called"):
    address: Address
    call_id: str
    name: str
    arguments: Mapping[str, object]
    person: PersonId | None = None


class ToolCompleted(Event, event_type="agent.tool.completed"):
    """`output` is what the model received: the result, or the reason of the failure."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
