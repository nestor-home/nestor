"""Doubles and contract suites for speaker identity.

The doubles treat audio as tagged PCM (`voice:mathis#2|` followed by a tone), so behaviour can be tested without
any model: each speaker has a voice of their own, each take of it differs a little, like two sentences do.
"""

import math
import random
from array import array
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.identity import (
    Learned,
    Profile,
    Vector,
    VoiceEmbedder,
    VoiceprintStore,
    VoiceSpace,
)
from nestor.modules.identity.audio import samples, similarity, unit

RATE = 16000
_TONE = 0.1  # of full scale: about -23 dBFS, a voice at a normal distance


def tagged(speaker: str, seconds: float = 3.0, *, take: int = 0, rate: int = RATE, level: float = _TONE) -> bytes:
    """Fake speech of `speaker` (their `take`-th sentence): its tag as quiet samples (one per character, then a 0),
    then a tone, up to `seconds` of 16-bit mono."""
    tag = [ord(c) for c in f"voice:{speaker}#{take}"] + [0]
    count = max(0, int(seconds * rate) - len(tag))
    tone = (int(level * 32767 * math.sin(2 * math.pi * 220 * n / rate)) for n in range(count))
    return array("h", [*tag, *tone]).tobytes()


def speaker_of(audio: bytes) -> tuple[str, int] | None:
    """The speaker and take of tagged audio."""
    pcm = samples(audio[:512])
    end = pcm.index(0) if 0 in pcm else 0
    text = "".join(chr(c) for c in pcm[:end] if 0 < c < 0x110000)
    if not text.startswith("voice:"):
        return None
    speaker, _, take = text[6:].partition("#")
    return speaker, int(take or 0)


class TaggedVoices(VoiceEmbedder):
    """A voice model for tagged audio: one direction per speaker, nudged by each take. Two takes of a voice are about
    0.9 alike, two voices about 0. `failing` makes it fail like a model that cannot run."""

    name = "tagged-voices"

    def __init__(self, *, dimensions: int = 32, variation: float = 0.3, threshold: float = 0.7) -> None:
        self._space = VoiceSpace(model="tagged", dimensions=dimensions)
        self._variation, self._threshold = variation, threshold
        self.failing = False
        self.calls = 0

    @property
    def space(self) -> VoiceSpace:
        return self._space

    @property
    def threshold(self) -> float:
        return self._threshold

    async def embed(self, audio: bytes) -> Vector:
        self.calls += 1
        if self.failing:
            raise ProviderError(self.name, "the model cannot run", transient=False)
        speaker, take = speaker_of(audio) or ("", 0)
        base = random.Random(f"voice:{speaker}")
        nudge = random.Random(f"voice:{speaker}#{take}")
        return unit([base.gauss() + self._variation * nudge.gauss() for _ in range(self._space.dimensions)])


class MemoryVoiceprintStore(VoiceprintStore):
    """Voiceprints kept in memory: for tests and benches."""

    name = "memory-voiceprints"

    def __init__(self) -> None:
        self.voices: dict[PersonId, tuple[str, Profile]] = {}  # person → (space id, profile)

    async def profiles(self, space: VoiceSpace) -> Mapping[PersonId, Profile]:
        return {person: profile for person, (found, profile) in self.voices.items() if found == space.id}

    async def enroll(
        self, person: PersonId, space: VoiceSpace, anchor: Sequence[Vector], *, learning: bool, at: datetime
    ) -> None:
        self.voices[person] = (space.id, Profile(anchor=tuple(anchor), learning=learning, enrolled_at=at))

    async def learn(self, person: PersonId, sample: Learned, *, keep: int, per_room: int) -> None:
        if person not in self.voices:
            raise ContractError(f"{person!r} has not recorded their voice")
        space, profile = self.voices[person]
        learned = sorted((*profile.learned, sample), key=lambda s: s.at)
        room = [s for s in learned if s.room == sample.room]
        dropped = {id(s) for s in room[: max(0, len(room) - per_room)]}
        learned = [s for s in learned if id(s) not in dropped]
        self.voices[person] = (space, replace(profile, learned=tuple(learned[max(0, len(learned) - keep) :])))

    async def unlearn(self, turns: Collection[str]) -> frozenset[PersonId]:
        changed: set[PersonId] = set()
        for person, (space, profile) in self.voices.items():
            kept = tuple(s for s in profile.learned if s.turn not in turns)
            if kept != profile.learned:
                changed.add(person)
                self.voices[person] = (space, replace(profile, learned=kept))
        return frozenset(changed)

    async def set_learning(self, person: PersonId, learning: bool) -> None:
        space, profile = self.voices[person]
        self.voices[person] = (space, replace(profile, learning=learning))

    async def forget(self, person: PersonId, *, learned_only: bool = False) -> None:
        if learned_only:
            space, profile = self.voices[person]
            self.voices[person] = (space, replace(profile, learned=()))
        else:
            self.voices.pop(person, None)

    async def keep_only(self, space: VoiceSpace) -> None:
        self.voices = {p: (s, profile) for p, (s, profile) in self.voices.items() if s == space.id}


class VoiceEmbedderContract:
    """Implement `embedder()` and `speech(speaker, take)`: a few seconds of that speaker's `take`-th sentence for
    this model (recordings for a real one)."""

    def embedder(self) -> VoiceEmbedder:
        raise NotImplementedError

    def speech(self, speaker: str, take: int) -> bytes:
        raise NotImplementedError

    async def test_a_voice_is_closer_to_itself_than_to_another(self) -> None:
        async with self.embedder() as embedder:
            first = unit(await embedder.embed(self.speech("a", 0)))
            again = unit(await embedder.embed(self.speech("a", 1)))
            other = unit(await embedder.embed(self.speech("b", 0)))
        assert len(first) == embedder.space.dimensions
        assert similarity(first, again) >= embedder.threshold > similarity(first, other)


def _sample(n: int, room: str = "salon", turn: str | None = None) -> Learned:
    return Learned(
        voiceprint=unit([1.0, float(n), 0.5]),
        turn=turn or f"t{n}",
        room=room,
        at=datetime(2026, 11, 4, tzinfo=UTC) + timedelta(minutes=n),
    )


class VoiceprintStoreContract:
    """Implement `store()`: an empty store, not started."""

    SPACE = VoiceSpace(model="m", dimensions=3)
    AT = datetime(2026, 11, 4, tzinfo=UTC)

    def store(self) -> VoiceprintStore:
        raise NotImplementedError

    async def test_an_enrolled_voice_comes_back_with_what_it_learned_oldest_first(self) -> None:
        lea = PersonId("lea")
        async with self.store() as store:
            await store.enroll(lea, self.SPACE, [unit([1.0, 0.0, 0.0])], learning=True, at=self.AT)
            await store.learn(lea, _sample(2), keep=50, per_room=20)
            await store.learn(lea, _sample(1, turn="t-early"), keep=50, per_room=20)
            profile = (await store.profiles(self.SPACE))[lea]
        assert profile.anchor == (unit([1.0, 0.0, 0.0]),) and profile.learning and profile.enrolled_at == self.AT
        assert [s.turn for s in profile.learned] == ["t-early", "t2"]
        assert profile.learned[0] == _sample(1, turn="t-early")

    async def test_learning_drops_the_oldest_beyond_the_limits(self) -> None:
        lea = PersonId("lea")
        async with self.store() as store:
            await store.enroll(lea, self.SPACE, [unit([1.0, 0.0, 0.0])], learning=True, at=self.AT)
            for n in range(5):
                await store.learn(lea, _sample(n, room="salon"), keep=4, per_room=3)
            await store.learn(lea, _sample(5, room="cuisine"), keep=4, per_room=3)
            learned = (await store.profiles(self.SPACE))[lea].learned
        assert [s.turn for s in learned] == ["t2", "t3", "t4", "t5"]  # 3 from the living room, then 4 in all

    async def test_unlearning_says_whose_voice_changed(self) -> None:
        lea, hugo = PersonId("lea"), PersonId("hugo")
        async with self.store() as store:
            for person in (lea, hugo):
                await store.enroll(person, self.SPACE, [unit([1.0, 0.0, 0.0])], learning=True, at=self.AT)
            await store.learn(lea, _sample(1), keep=50, per_room=20)
            await store.learn(hugo, _sample(2), keep=50, per_room=20)
            changed = await store.unlearn({"t1", "t9"})
            profiles = await store.profiles(self.SPACE)
        assert changed == {lea}
        assert profiles[lea].learned == () and len(profiles[hugo].learned) == 1

    async def test_enrolling_again_starts_over_and_forgetting_erases(self) -> None:
        lea, hugo = PersonId("lea"), PersonId("hugo")
        async with self.store() as store:
            for person in (lea, hugo):
                await store.enroll(person, self.SPACE, [unit([1.0, 0.0, 0.0])], learning=True, at=self.AT)
                await store.learn(person, _sample(1, turn=f"t-{person}"), keep=50, per_room=20)
            await store.enroll(lea, self.SPACE, [unit([0.0, 1.0, 0.0])], learning=False, at=self.AT)
            again = (await store.profiles(self.SPACE))[lea]
            await store.forget(hugo, learned_only=True)
            await store.set_learning(hugo, False)
            hugo_now = (await store.profiles(self.SPACE))[hugo]
            await store.forget(lea)
            left = await store.profiles(self.SPACE)
        assert again.anchor == (unit([0.0, 1.0, 0.0]),) and again.learned == () and not again.learning
        assert hugo_now.learned == () and hugo_now.anchor and not hugo_now.learning
        assert set(left) == {hugo}

    async def test_another_model_keeps_nothing_of_the_previous(self) -> None:
        lea, other = PersonId("lea"), VoiceSpace(model="n", dimensions=3)
        async with self.store() as store:
            await store.enroll(lea, self.SPACE, [unit([1.0, 0.0, 0.0])], learning=True, at=self.AT)
            assert await store.profiles(other) == {}
            await store.keep_only(other)
            assert await store.profiles(self.SPACE) == {}
