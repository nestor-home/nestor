"""Events of tool calls: what the agent did, with which arguments, and what came back, in the
conversation and turn (`exchange`) the call was made in, when there is one."""

from collections.abc import Mapping

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange


class ToolCalled(Event, event_type="agent.tool.called"):
    address: Address
    call_id: str
    name: str
    arguments: Mapping[str, object]
    person: PersonId | None = None
    exchange: Exchange | None = None


class ToolCompleted(Event, event_type="agent.tool.completed"):
    """`output` is what the model received: the result, or the reason of the failure."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
    exchange: Exchange | None = None
