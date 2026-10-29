"""Values of the dialogue, shared by every channel."""

from enum import StrEnum


class FallbackReason(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_SLOW = "model_slow"
    RECOGNITION_UNAVAILABLE = "recognition_unavailable"
    SYNTHESIS_UNAVAILABLE = "synthesis_unavailable"
