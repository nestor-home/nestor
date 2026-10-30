"""Identity: who speaks when (diarization) and who that is (speaker identification), opt-in.

Recognising a voice personalises the conversation; it never authorises a sensitive action on its own.
Models are chosen later on benchmarks: these ports and their doubles come first.
"""

from nestor.modules.identity.events import SpeakerEnrolled, SpeakerForgotten, SpeakerIdentified
from nestor.modules.identity.ports import Diarizer, SpeakerIdentifier
from nestor.modules.identity.types import Identification, Segment, SpeakerLabel, Voiceprint

__all__ = [
    "Diarizer",
    "Identification",
    "Segment",
    "SpeakerEnrolled",
    "SpeakerForgotten",
    "SpeakerIdentified",
    "SpeakerIdentifier",
    "SpeakerLabel",
    "Voiceprint",
]
