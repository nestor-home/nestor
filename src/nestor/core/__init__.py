"""Vendor-free kernel shared by every module.

- `contracts`: `Component` lifecycle and capabilities, model types, and what a call consumes (`report`)
- `events`: versioned events and their log records
- `shared`: identifiers and time helpers
- `exceptions`: the error hierarchy
"""

from nestor.core.contracts import (
    Capabilities,
    Capability,
    Component,
    Health,
    Model,
    ModelType,
    Money,
    Tally,
    Unit,
    Usage,
    counted,
    counting,
    report,
)
from nestor.core.events import Event, Record
from nestor.core.exceptions import CapabilityMissing, ContractError, NestorError, ProviderError
from nestor.core.shared import Day, PersonId, SessionId, byte_size, new_id, shorten, utc_now

__all__ = [
    "Capabilities",
    "Capability",
    "CapabilityMissing",
    "Component",
    "ContractError",
    "Day",
    "Event",
    "Health",
    "Model",
    "ModelType",
    "Money",
    "NestorError",
    "PersonId",
    "ProviderError",
    "Record",
    "SessionId",
    "Tally",
    "Unit",
    "Usage",
    "byte_size",
    "counted",
    "counting",
    "new_id",
    "report",
    "shorten",
    "utc_now",
]
