"""Events of tool calls: what the agent did, with which arguments, and what came back.

v2: `exchange`, the conversation and turn the call was made in (`None` in version 1 records).
"""

from collections.abc import Mapping

from nestor.core import Event, PersonId
from nestor.core.events import JSON
from nestor.modules.channels import Address, Exchange, before_exchanges


class ToolCalled(Event, event_type="agent.tool.called", version=2):
    address: Address
    call_id: str
    name: str
    arguments: Mapping[str, object]
    person: PersonId | None = None
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)


class ToolCompleted(Event, event_type="agent.tool.completed", version=2):
    """`output` is what the model received: the result, or the reason of the failure."""

    call_id: str
    name: str
    output: str
    ok: bool
    duration_s: float
    exchange: Exchange | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, JSON]) -> dict[str, JSON]:
        return before_exchanges(payload)
