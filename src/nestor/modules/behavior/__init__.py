"""Behavior: the assistant's attitude and expressions, translated by whichever body is plugged in."""

from nestor.modules.behavior.events import BehaviorChanged, ExpressionRequested
from nestor.modules.behavior.ports import Body
from nestor.modules.behavior.types import EXPRESSION, HEAD_MOTION, Behavior, Expression

__all__ = ["EXPRESSION", "HEAD_MOTION", "Behavior", "BehaviorChanged", "Body", "Expression", "ExpressionRequested"]
