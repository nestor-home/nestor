"""Identity events: consent and its withdrawal are recorded; voices themselves never are."""

from nestor.core import Event, PersonId


class VoiceEnrolled(Event, event_type="voice.enrolled"):
    """A person recorded their voice, agreeing to keep a voiceprint of it (`learning`: improved over time)."""

    person: PersonId
    by: PersonId | None  # who ran the recording: themselves, or the owner for someone without an account
    where: str  # "admin", or the room of a satellite
    learning: bool


class VoiceForgotten(Event, event_type="voice.forgotten"):
    """A person's voice was erased: all of it, or only what was learned since the recording."""

    person: PersonId
    by: PersonId | None
    learned_only: bool = False


class VoiceLearningChanged(Event, event_type="voice.learning.changed"):
    person: PersonId
    by: PersonId | None
    learning: bool
