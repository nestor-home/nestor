"""Voices: recording a voice with consent, recognising it, learning it over time, forgetting it."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nestor.core import ContractError, PersonId
from nestor.modules.identity import (
    Problem,
    VoiceEnrolled,
    VoiceForgotten,
    VoiceLearningChanged,
    Voices,
    VoiceSettings,
    VoiceSpace,
)
from nestor.modules.journal import Journal
from nestor.testing.identity import (
    MemoryVoiceprintStore,
    TaggedVoices,
    VoiceEmbedderContract,
    VoiceprintStoreContract,
    tagged,
)
from nestor.testing.journal import MemoryEventLog

LEA, HUGO = PersonId("lea"), PersonId("hugo")


class TestTaggedVoices(VoiceEmbedderContract):
    def embedder(self) -> TaggedVoices:
        return TaggedVoices()

    def speech(self, speaker: str, take: int) -> bytes:
        return tagged(speaker, take=take)


class TestMemoryVoiceprintStore(VoiceprintStoreContract):
    def store(self) -> MemoryVoiceprintStore:
        return MemoryVoiceprintStore()


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, 18, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def voices(store: MemoryVoiceprintStore | None = None, **settings: Any) -> tuple[Voices, Journal, Clock]:
    journal, clock = Journal(MemoryEventLog()), Clock()
    settled = VoiceSettings(**settings)
    return (
        Voices(TaggedVoices(), store or MemoryVoiceprintStore(), journal, clock=clock, settings=settled),
        journal,
        clock,
    )


async def enroll(voices: Voices, person: PersonId, speaker: str | None = None, *, learning: bool = True) -> None:
    enrollment = voices.begin(person, by=person, where="admin", learning=learning)
    for phrase in range(len(enrollment.phrases)):
        assert (await voices.take(enrollment.id, phrase, tagged(speaker or person, take=100 + phrase))).ok
    await voices.finish(enrollment.id)


async def test_nobody_is_recognised_before_anyone_records_their_voice() -> None:
    found, _, _ = voices()
    async with found:
        heard = await found.hear(tagged("lea"))
    assert heard.person is None and heard.voiceprint is not None


async def test_a_recorded_voice_is_recognised_and_a_stranger_is_not() -> None:
    found, journal, _ = voices()
    async with found:
        await enroll(found, LEA)
        await enroll(found, HUGO)
        lea, stranger = await found.hear(tagged("lea", take=1)), await found.hear(tagged("someone"))
    assert lea.person == LEA and lea.score >= found.threshold and lea.margin > 0.5
    assert stranger.person is None
    enrolled = await journal.history(VoiceEnrolled)
    assert [e.person for e in enrolled] == [LEA, HUGO]


async def test_speech_too_short_or_a_model_that_fails_recognises_nobody() -> None:
    found, _, _ = voices()
    async with found:
        await enroll(found, LEA)
        short = await found.hear(tagged("lea", 0.5))
        assert isinstance(found.embedder, TaggedVoices)
        found.embedder.failing = True
        failed = await found.hear(tagged("lea"))
    assert short.person is None and short.voiceprint is None
    assert failed.person is None and failed.voiceprint is None


@pytest.mark.parametrize(
    ("audio", "problem"),
    [
        (tagged("lea", 0.6), Problem.TOO_SHORT),
        (tagged("lea", level=0.0), Problem.TOO_QUIET),
        (tagged("lea", level=1.0), Problem.TOO_LOUD),
        (tagged("hugo"), Problem.OTHER_VOICE),
    ],
)
async def test_a_phrase_that_cannot_serve_is_asked_again(audio: bytes, problem: Problem) -> None:
    found, _, _ = voices()
    async with found:
        enrollment = found.begin(LEA, by=LEA, where="admin")
        assert (await found.take(enrollment.id, 0, tagged("lea", take=1))).ok
        check = await found.take(enrollment.id, 1, audio)
        with pytest.raises(ContractError, match="missing"):
            await found.finish(enrollment.id)
    assert check.problem is problem and check.taken == 1 and enrollment.next == 1


async def test_a_recording_left_alone_is_dropped_and_a_new_one_replaces_it() -> None:
    found, _, clock = voices()
    async with found:
        first = found.begin(LEA, by=LEA, where="salon")
        second = found.begin(LEA, by=LEA, where="admin")
        assert found.enrolling("salon") is None and found.enrolling("admin") is second
        clock.now += timedelta(minutes=11)
        with pytest.raises(ContractError, match="over"):
            await found.take(second.id, 0, tagged("lea"))
    with pytest.raises(ContractError):
        found.enrollment(first.id)


async def test_recording_again_replaces_the_voice_and_what_it_learned() -> None:
    found, _, _ = voices()
    async with found:
        await enroll(found, LEA)
        assert await found.learn(await found.hear(tagged("lea", take=1)), turn="t1", room="salon")
        await enroll(found, LEA, "lea")
        status = found.status(LEA)
    assert status.enrolled and status.learned == 0


async def test_a_clear_turn_is_learned_and_a_doubtful_one_is_not() -> None:
    found, _, _ = voices()
    async with found:
        await enroll(found, LEA)
        clear = await found.learn(await found.hear(tagged("lea", take=1)), turn="t1", room="salon")
        short = await found.learn(await found.hear(tagged("lea", 1.5, take=2)), turn="t2", room="salon")
        stranger = await found.learn(await found.hear(tagged("someone")), turn="t3", room="salon")
        status = found.status(LEA)
    assert clear and not short and not stranger
    assert status.learned == 1 and status.last_learned_at is not None


async def test_learning_keeps_the_newest_turns_of_each_room_and_in_all() -> None:
    """Each limit holds on its own: `per_room` while the total is under `keep`, then `keep` across rooms."""
    store = MemoryVoiceprintStore()
    found, _, clock = voices(store, keep=3, per_room=2)

    async def learn(take: int, turn: str, room: str) -> None:
        clock.now += timedelta(minutes=1)
        assert await found.learn(await found.hear(tagged("lea", take=take)), turn=turn, room=room)

    async def kept() -> list[str]:
        return [s.turn for s in (await store.profiles(found.embedder.space))[LEA].learned]

    async with found:
        await enroll(found, LEA)
        for take in range(4):
            await learn(take, f"s{take}", "salon")
        in_the_living_room = await kept()
        await learn(8, "k1", "cuisine")
        await learn(9, "k2", "cuisine")
        in_all = await kept()
    assert in_the_living_room == ["s2", "s3"], "two per room, though three in all would fit"
    assert in_all == ["s3", "k1", "k2"], "three in all, though each room keeps two"
    assert found.status(LEA).learned == 3


async def test_learning_stops_when_the_person_says_so() -> None:
    found, journal, _ = voices()
    async with found:
        await enroll(found, LEA)
        await found.set_learning(LEA, False, by=LEA)
        refused = await found.learn(await found.hear(tagged("lea", take=5)), turn="t", room="salon")
    assert not refused and not found.status(LEA).learning and found.status(LEA).learned == 0
    assert [e.learning for e in await journal.history(VoiceLearningChanged)] == [False]


async def test_learned_turns_weigh_alongside_the_recording() -> None:
    found, _, _ = voices()
    async with found:
        await enroll(found, LEA)
        before = (await found.hear(tagged("lea", take=7))).score
        for turn in range(1, 5):  # her voice as the room hears it, turn after turn
            await found.learn(await found.hear(tagged("lea", take=7)), turn=f"t{turn}", room="salon")
        after = await found.hear(tagged("lea", take=7))
    assert after.person == LEA and after.score > before


async def test_forgetting_erases_the_voice_or_only_what_was_learned() -> None:
    store = MemoryVoiceprintStore()
    found, journal, _ = voices(store)
    async with found:
        await enroll(found, LEA)
        await found.learn(await found.hear(tagged("lea", take=1)), turn="t1", room="salon")
        await found.forget(LEA, by=LEA, learned_only=True)
        learned_gone = found.status(LEA)
        await found.forget(LEA, by=None)
        heard = await found.hear(tagged("lea", take=2))
        with pytest.raises(ContractError, match="not recorded"):
            await found.forget(LEA, by=None)
    assert learned_gone.enrolled and learned_gone.learned == 0
    assert heard.person is None and store.voices == {} and not found.status(LEA).enrolled
    assert [e.learned_only for e in await journal.history(VoiceForgotten)] == [True, False]


async def test_voices_of_another_model_are_erased_on_start() -> None:
    store = MemoryVoiceprintStore()
    await store.enroll(LEA, VoiceSpace(model="older", dimensions=32), [(1.0,) * 32], learning=True, at=Clock()())
    found, _, _ = voices(store)
    async with found:
        assert not found.status(LEA).enrolled
    assert store.voices == {}


async def test_the_configured_threshold_wins_over_the_models() -> None:
    store = MemoryVoiceprintStore()
    async with voices(store)[0] as found:
        await enroll(found, LEA)
    async with voices(store, threshold=0.99)[0] as strict:
        heard = await strict.hear(tagged("lea", take=1))
    assert strict.threshold == 0.99 and heard.person is None and heard.score > 0.7
