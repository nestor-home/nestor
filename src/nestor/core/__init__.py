"""Vendor-free kernel shared by every module.

- `contracts`: `Component` lifecycle and capabilities
- `events`: versioned events and their log records
- `shared`: identifiers and time helpers
- `exceptions`: the error hierarchy
"""

from nestor.core.contracts import Capabilities, Capability, Component
from nestor.core.events import Event, Record
from nestor.core.exceptions import CapabilityMissing, ContractError, NestorError, ProviderError
from nestor.core.shared import PersonId, SessionId, new_id, utc_now

__all__ = [
    "Capabilities",
    "Capability",
    "CapabilityMissing",
    "Component",
    "ContractError",
    "Event",
    "NestorError",
    "PersonId",
    "ProviderError",
    "Record",
    "SessionId",
    "new_id",
    "utc_now",
]
