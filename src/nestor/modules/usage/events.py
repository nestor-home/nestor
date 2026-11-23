"""The ledger's one event: a call, what it consumed, what it cost and on whose behalf."""

from collections.abc import Mapping

from nestor.core import Event, PersonId
from nestor.modules.channels import Medium
from nestor.modules.usage.types import CallPurpose, ConsumerKind, CostBasis, Outcome


class UsageRecorded(Event, event_type="usage.recorded"):
    """One call to a model or an executor. Its cost is fixed when it is recorded, with where its price came from:
    a later price never rewrites it. `session` (the envelope's) is the address the work belongs to."""

    consumer: str  # its name in the configuration
    kind: ConsumerKind
    provider: str  # who bills it
    served: str | None  # the model that answered, as the provider names it
    units: Mapping[str, float]  # by `Unit`
    cost_nusd: int | None  # nano-dollars; none when unknown
    basis: CostBasis
    price: str | None  # `reported`, `local`, `config`, `catalogue:<date>`
    duration_ms: int
    outcome: Outcome
    purpose: CallPurpose
    person: PersonId | None = None
    channel: str | None = None
    medium: Medium | None = None
    conversation: str | None = None
    turn: str | None = None
    origin: str | None = None
