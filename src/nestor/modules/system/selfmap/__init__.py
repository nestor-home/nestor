"""What Nestor knows of itself: a card per part (what it enables, what it needs, its documentation), the map of the
parts plugged in, installed or missing here, and the tool the agent consults it with."""

from nestor.modules.system.selfmap.assistant import AboutNestor
from nestor.modules.system.selfmap.ports import Documentation
from nestor.modules.system.selfmap.service import SelfMap, describe
from nestor.modules.system.selfmap.types import Capability, Card, Need, Part, Standing

__all__ = ["AboutNestor", "Capability", "Card", "Documentation", "Need", "Part", "SelfMap", "Standing", "describe"]
