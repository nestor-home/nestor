"""Identity events: consent and its withdrawal are recorded; voices themselves never are."""

from nestor.core import Event, PersonId


class SpeakerEnrolled(Event, event_type="identity.enrolled"):
    person: PersonId


class SpeakerForgotten(Event, event_type="identity.forgotten"):
    person: PersonId


class SpeakerIdentified(Event, event_type="observation.speaker.identified"):
    person: PersonId | None
    confidence: float
