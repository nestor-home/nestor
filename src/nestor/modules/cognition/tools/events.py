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
    """The call answered within the turn: `output` is what the model received, the result (its start and end, when
    too long) or the reason of the failure."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
    exchange: Exchange | None = None


class ToolDeferred(Event, event_type="agent.tool.deferred"):
    """The call did not answer within the turn's wait and goes on in the background: `output` is what the model
    received instead of the result, which comes back later as `ToolReturned`, to `person` at `address`."""

    address: Address
    call_id: str
    name: str
    arguments: Mapping[str, object]
    output: str
    person: PersonId | None = None
    exchange: Exchange | None = None


class ToolReturned(Event, event_type="agent.tool.returned"):
    """The result of a deferred call, once it ends: it comes back to the conversation as a notification."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
    exchange: Exchange | None = None


class ResultStored(Event, event_type="agent.tool.result-stored"):
    """A result too large for the turn went to the blob store: who may read it back."""

    ref: str  # the blob's digest
    size: int  # characters
    call_id: str
    address: Address
    person: PersonId | None = None
