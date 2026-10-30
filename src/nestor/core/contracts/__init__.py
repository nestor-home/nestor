"""What every pluggable component shares: a lifecycle and declared capabilities."""

from nestor.core.contracts.capabilities import Capabilities, Capability
from nestor.core.contracts.component import Component, Health

__all__ = ["Capabilities", "Capability", "Component", "Health"]
