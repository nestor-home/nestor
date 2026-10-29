"""Events of the behavior engine."""

from nestor.core import Event
from nestor.modules.behavior.types import Behavior, Expression


class BehaviorChanged(Event, event_type="behavior.changed"):
    behavior: Behavior


class ExpressionRequested(Event, event_type="expression.requested"):
    expression: Expression
    intensity: float = 1.0
