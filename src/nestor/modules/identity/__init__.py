"""Identity: who speaks, opt-in. A satellite is a place: who speaks there is told turn by turn, by their voice when
they recorded it, by what they say otherwise, and nobody in particular when neither tells.

Recognising a voice personalises the conversation; it never authorises a sensitive action on its own.
"""

from nestor.modules.identity.events import VoiceEnrolled, VoiceForgotten, VoiceLearningChanged
from nestor.modules.identity.ports import VoiceEmbedder, VoiceprintStore
from nestor.modules.identity.service import (
    PHRASES,
    Check,
    Departures,
    Enrollment,
    Problem,
    Voices,
    VoiceSettings,
    VoiceStatus,
)
from nestor.modules.identity.types import (
    Heard,
    Identified,
    Learned,
    Profile,
    Speaker,
    Vector,
    VoiceSpace,
)

__all__ = [
    "PHRASES",
    "Check",
    "Departures",
    "Enrollment",
    "Heard",
    "Identified",
    "Learned",
    "Problem",
    "Profile",
    "Speaker",
    "Vector",
    "VoiceEmbedder",
    "VoiceEnrolled",
    "VoiceForgotten",
    "VoiceLearningChanged",
    "VoiceSettings",
    "VoiceSpace",
    "VoiceStatus",
    "VoiceprintStore",
    "Voices",
]
