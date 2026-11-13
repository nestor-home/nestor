"""Events of tool calls: what the agent did, with which arguments, and what came back, in the
conversation and turn (`exchange`) the call was made in, when there is one."""

from collections.abc import Mapping

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.journal import BlobRef


class ToolCalled(Event, event_type="agent.tool.called"):
    """`connection_id`: the connected account the tool acts on, when it is one of an account's."""

    address: Address
    call_id: str
    name: str
    arguments: Mapping[str, object]
    person: PersonId | None = None
    exchange: Exchange | None = None
    connection_id: str | None = None


class ToolCompleted(Event, event_type="agent.tool.completed"):
    """The call answered within the turn: `output` is what the model received, the result (its start and end, when
    too long) or the reason of the failure; `files`, what it made, to go with the answer."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
    files: tuple[BlobRef, ...] = ()
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
    files: tuple[BlobRef, ...] = ()  # what it made, to go with the answer to its notification
    exchange: Exchange | None = None


class ResultStored(Event, event_type="agent.tool.result-stored"):
    """A text too large for the turn went to the blob store, a tool's result or a document's: who may read it back."""

    ref: str  # the blob's digest
    size: int  # characters
    call_id: str | None = None  # the call whose result it is; none for a document someone sent
    address: Address
    person: PersonId | None = None
