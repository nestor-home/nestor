"""Voices: who speaks, from their voice, with their consent.

A voice model (`VoiceEmbedder`) turns speech into a voiceprint; everything else is here, the same for every model:

- recognising: a turn's voiceprint is compared with each enrolled person's, the anchor (the recording they
  agreed to) weighing a fixed share so that learning cannot drift away from it;
- learning: a turn recognised with a clear margin adds to the person's voice, at most `keep` of them, at most
  `per_room` from one room; a correction takes back what its conversation taught;
- enrolling: a session asks for a few phrases, checks each one (long enough, loud enough, the same voice as
  the others) and keeps their voiceprints as the anchor, never the audio.
"""

import asyncio
import contextlib
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum

from nestor.core import Component, ContractError, PersonId, ProviderError, new_id, utc_now
from nestor.modules.identity.audio import centroid, clipped, duration_s, level_dbfs, samples, similarity, unit
from nestor.modules.identity.events import VoiceEnrolled, VoiceForgotten, VoiceLearningChanged
from nestor.modules.identity.ports import VoiceEmbedder, VoiceprintStore
from nestor.modules.identity.types import Heard, Learned, Profile, Vector
from nestor.modules.journal import Journal

PHRASES = tuple(f"voice-phrase-{n}" for n in range(1, 6))  # what a person reads to enroll, in their language


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceSettings:
    """How voices are told apart and learned; `threshold` defaults to the model's own, calibrated on the bench."""

    threshold: float | None = None
    anchor_weight: float = 0.5  # the anchor's share of a score once something was learned
    min_s: float = 1.0  # shorter speech says too little: nobody is recognised
    learn_min_s: float = 2.0
    learn_margin: float = 0.1  # above the threshold, for a turn to be learned
    learn_lead: float = 0.15  # ahead of the next person, for a turn to be learned
    keep: int = 50
    per_room: int = 20
    nearest: int = 3  # learned voiceprints a turn is compared with
    min_phrase_s: float = 1.0
    quiet_dbfs: float = -45.0
    clipped_share: float = 0.001
    enrollment_s: float = 600.0  # an enrollment left alone this long is dropped


class Problem(StrEnum):
    """Why a phrase of an enrollment is asked again."""

    TOO_SHORT = "too_short"
    TOO_QUIET = "too_quiet"
    TOO_LOUD = "too_loud"
    OTHER_VOICE = "other_voice"


@dataclass(frozen=True, slots=True, kw_only=True)
class Check:
    """The answer to one phrase: kept, or why not; how many are kept out of how many."""

    problem: Problem | None
    taken: int
    total: int

    @property
    def ok(self) -> bool:
        return self.problem is None

    @property
    def complete(self) -> bool:
        return self.taken == self.total


@dataclass(slots=True, kw_only=True)
class Enrollment:
    """A recording in progress: its phrases (message ids), the voiceprints kept so far by phrase."""

    id: str
    person: PersonId
    by: PersonId | None
    where: str  # "admin", or the room of a satellite
    learning: bool
    phrases: tuple[str, ...]
    expires_at: datetime
    taken: dict[int, Vector] = field(default_factory=dict)

    @property
    def next(self) -> int | None:
        """The first phrase still to say."""
        return next((i for i in range(len(self.phrases)) if i not in self.taken), None)


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceStatus:
    enrolled: bool
    learning: bool = False
    learned: int = 0
    enrolled_at: datetime | None = None
    last_learned_at: datetime | None = None


class Voices(Component):
    """Contract: `start` loads the profiles of the model's space and erases those of another; recognising never
    fails a turn (a model that cannot run gives nobody); nothing about a voice reaches the journal."""

    name = "voices"

    def __init__(
        self,
        embedder: VoiceEmbedder,
        store: VoiceprintStore,
        journal: Journal,
        *,
        settings: VoiceSettings | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.embedder, self.store, self.journal = embedder, store, journal
        self.settings = settings or VoiceSettings()
        self._clock = clock
        self._profiles: dict[PersonId, Profile] = {}
        self._anchors: dict[PersonId, Vector] = {}  # each profile's anchor, averaged once
        self._enrollments: dict[str, Enrollment] = {}
        self._writing = asyncio.Lock()  # profile changes are written one at a time, cache and store together

    @property
    def threshold(self) -> float:
        return self.settings.threshold if self.settings.threshold is not None else self.embedder.threshold

    async def start(self) -> None:
        space = self.embedder.space
        await self.store.keep_only(space)
        for person, profile in (await self.store.profiles(space)).items():
            self._keep(person, profile)

    def status(self, person: PersonId) -> VoiceStatus:
        profile = self._profiles.get(person)
        if profile is None:
            return VoiceStatus(enrolled=False)
        return VoiceStatus(
            enrolled=True,
            learning=profile.learning,
            learned=len(profile.learned),
            enrolled_at=profile.enrolled_at,
            last_learned_at=profile.learned[-1].at if profile.learned else None,
        )

    # --- recognising --------------------------------------------------------------------------------

    async def hear(self, audio: bytes) -> Heard:
        """Who said `audio`, as far as their voice tells; nobody when it is too short, unknown or the model fails."""
        space = self.embedder.space.id
        seconds = duration_s(audio, self.embedder.sample_rate)
        if seconds < self.settings.min_s:
            return Heard(space=space, voiceprint=None, duration_s=seconds)
        try:
            voiceprint = unit(await self.embedder.embed(audio))
        except ProviderError:
            return Heard(space=space, voiceprint=None, duration_s=seconds)
        scores = sorted(((self._score(voiceprint, person), person) for person in self._profiles), reverse=True)
        best, person = scores[0] if scores else (0.0, None)
        second = scores[1][0] if len(scores) > 1 else 0.0
        return Heard(
            space=space,
            voiceprint=voiceprint,
            duration_s=seconds,
            person=person if best >= self.threshold else None,
            score=best,
            margin=best - second,
        )

    def _score(self, voiceprint: Vector, person: PersonId) -> float:
        profile = self._profiles[person]
        anchor = similarity(voiceprint, self._anchors[person])
        if len(profile.learned) < self.settings.nearest:
            return anchor
        nearest = sorted((similarity(voiceprint, s.voiceprint) for s in profile.learned), reverse=True)
        learned = sum(nearest[: self.settings.nearest]) / self.settings.nearest
        weight = self.settings.anchor_weight
        return weight * anchor + (1 - weight) * learned

    # --- learning -----------------------------------------------------------------------------------

    async def learn(self, heard: Heard, *, turn: str, room: str) -> bool:
        """Add a recognised turn to the person's voice when it is clear enough to; says whether it did."""
        person, settings = heard.person, self.settings
        profile = self._profiles.get(person) if person else None
        clear = (
            heard.voiceprint is not None
            and heard.space == self.embedder.space.id
            and heard.duration_s >= settings.learn_min_s
            and heard.score >= self.threshold + settings.learn_margin
            and heard.margin >= settings.learn_lead
        )
        if person is None or profile is None or not profile.learning or not clear:
            return False
        assert heard.voiceprint is not None
        sample = Learned(voiceprint=heard.voiceprint, turn=turn, room=room, at=self._clock())
        async with self._writing:
            await self.store.learn(person, sample, keep=settings.keep, per_room=settings.per_room)
            self._keep(person, replace(profile, learned=_kept((*profile.learned, sample), settings)))
        return True

    async def unlearn(self, turns: Collection[str]) -> None:
        """Take back what these turns taught: they were not who their voice seemed to be."""
        if not turns:
            return
        async with self._writing:
            changed = await self.store.unlearn(turns)
            for person in changed & self._profiles.keys():
                profile = self._profiles[person]
                self._keep(person, replace(profile, learned=tuple(s for s in profile.learned if s.turn not in turns)))

    async def set_learning(self, person: PersonId, learning: bool, *, by: PersonId | None) -> None:
        profile = self._enrolled(person)
        async with self._writing:
            await self.store.set_learning(person, learning)
            self._keep(person, replace(profile, learning=learning))
        await self.journal.publish(VoiceLearningChanged(source=self.name, person=person, by=by, learning=learning))

    async def forget(self, person: PersonId, *, by: PersonId | None, learned_only: bool = False) -> None:
        profile = self._enrolled(person)
        async with self._writing:
            await self.store.forget(person, learned_only=learned_only)
            if learned_only:
                self._keep(person, replace(profile, learned=()))
            else:
                del self._profiles[person], self._anchors[person]
        await self.journal.publish(VoiceForgotten(source=self.name, person=person, by=by, learned_only=learned_only))

    def _keep(self, person: PersonId, profile: Profile) -> None:
        self._profiles[person] = profile
        self._anchors[person] = centroid(profile.anchor)

    def _enrolled(self, person: PersonId) -> Profile:
        profile = self._profiles.get(person)
        if profile is None:
            raise ContractError(f"{person!r} has not recorded their voice")
        return profile

    # --- enrolling ----------------------------------------------------------------------------------

    def begin(self, person: PersonId, *, by: PersonId | None, where: str, learning: bool = True) -> Enrollment:
        """Start recording a person's voice; a previous recording of theirs that was not finished is dropped."""
        self._drop_expired()
        for found in [e for e in self._enrollments.values() if e.person == person or e.where == where]:
            del self._enrollments[found.id]
        enrollment = Enrollment(
            id=new_id(),
            person=person,
            by=by,
            where=where,
            learning=learning,
            phrases=PHRASES,
            expires_at=self._clock() + timedelta(seconds=self.settings.enrollment_s),
        )
        self._enrollments[enrollment.id] = enrollment
        return enrollment

    def enrollment(self, enrollment_id: str) -> Enrollment:
        self._drop_expired()
        try:
            return self._enrollments[enrollment_id]
        except KeyError:
            raise ContractError("this voice recording is over: start again") from None

    def enrolling(self, where: str) -> Enrollment | None:
        """The recording going on in a room, if any."""
        self._drop_expired()
        return next((e for e in self._enrollments.values() if e.where == where), None)

    async def take(self, enrollment_id: str, phrase: int, audio: bytes) -> Check:
        """Check one phrase of a recording (its audio, from a browser) and keep its voiceprint when it passes."""
        enrollment = self._phrase(enrollment_id, phrase)
        problem = self._problem(audio)
        if problem is None:
            problem = self._keep_phrase(enrollment, phrase, unit(await self.embedder.embed(audio)))
        return Check(problem=problem, taken=len(enrollment.taken), total=len(enrollment.phrases))

    def take_heard(self, enrollment_id: str, phrase: int, heard: Heard | None) -> Check:
        """Check one phrase said to a satellite, from what its voice already gave (the turn's `Heard`)."""
        enrollment = self._phrase(enrollment_id, phrase)
        voiceprint = heard.voiceprint if heard is not None and heard.space == self.embedder.space.id else None
        if voiceprint is None or heard is None or heard.duration_s < self.settings.min_phrase_s:
            problem: Problem | None = Problem.TOO_SHORT
        else:
            problem = self._keep_phrase(enrollment, phrase, voiceprint)
        return Check(problem=problem, taken=len(enrollment.taken), total=len(enrollment.phrases))

    def _phrase(self, enrollment_id: str, phrase: int) -> Enrollment:
        enrollment = self.enrollment(enrollment_id)
        if not 0 <= phrase < len(enrollment.phrases):
            raise ContractError(f"no phrase {phrase} in this recording")
        return enrollment

    def _keep_phrase(self, enrollment: Enrollment, phrase: int, voiceprint: Vector) -> Problem | None:
        """Keep a phrase's voiceprint unless it is another voice than the phrases kept so far."""
        others = [v for i, v in enrollment.taken.items() if i != phrase]
        if others and similarity(voiceprint, centroid(others)) < self.threshold:
            return Problem.OTHER_VOICE
        enrollment.taken[phrase] = voiceprint
        return None

    async def finish(self, enrollment_id: str) -> None:
        """Keep the recording: its phrases' voiceprints become the person's anchor, and anything learned before
        goes with the previous one."""
        enrollment = self.enrollment(enrollment_id)
        if enrollment.next is not None:
            raise ContractError("some phrases are still missing")
        anchor = tuple(enrollment.taken[i] for i in range(len(enrollment.phrases)))
        at = self._clock()
        async with self._writing:
            await self.store.enroll(enrollment.person, self.embedder.space, anchor, learning=enrollment.learning, at=at)
            self._keep(enrollment.person, Profile(anchor=anchor, learning=enrollment.learning, enrolled_at=at))
        del self._enrollments[enrollment.id]
        await self.journal.publish(
            VoiceEnrolled(
                source=self.name,
                person=enrollment.person,
                by=enrollment.by,
                where=enrollment.where,
                learning=enrollment.learning,
            )
        )

    def abandon(self, enrollment_id: str) -> None:
        with contextlib.suppress(KeyError):
            del self._enrollments[enrollment_id]

    def _problem(self, audio: bytes) -> Problem | None:
        settings, pcm = self.settings, samples(audio)
        if duration_s(audio, self.embedder.sample_rate) < settings.min_phrase_s:
            return Problem.TOO_SHORT
        if clipped(pcm) > settings.clipped_share:
            return Problem.TOO_LOUD
        if level_dbfs(pcm) < settings.quiet_dbfs:
            return Problem.TOO_QUIET
        return None

    def _drop_expired(self) -> None:
        now = self._clock()
        for found in [e for e in self._enrollments.values() if e.expires_at <= now]:
            del self._enrollments[found.id]


def _kept(learned: tuple[Learned, ...], settings: VoiceSettings) -> tuple[Learned, ...]:
    """What remains once the oldest are dropped beyond `per_room` in a room, then beyond `keep` in all (the
    store's rule, applied to the cache)."""
    kept: list[Learned] = []
    rooms: dict[str, int] = {}
    for sample in reversed(learned):
        if rooms.get(sample.room, 0) < settings.per_room and len(kept) < settings.keep:
            rooms[sample.room] = rooms.get(sample.room, 0) + 1
            kept.append(sample)
    return tuple(reversed(kept))
