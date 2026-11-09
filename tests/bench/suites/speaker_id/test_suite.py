"""The speaker-id suite on a household of tagged voices (no model to download): enrolling through the core, telling
voices apart, keeping impostors out, learning, and what a bad model gets wrong."""

import json
import wave
from array import array
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from nestor.bench import BenchError
from nestor.bench.recording import Cache
from nestor.bench.results import Run
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.suites.speaker_id import SpeakerId
from nestor.bench.suites.speaker_id.store import MemoryVoiceprints
from nestor.bench.suites.speaker_id.suite import accepted, equal_error_rate, read_pcm, threshold_for
from nestor.bench.variants import load_variant
from nestor.core import ProviderError
from nestor.modules.identity import SpeakerModel, Vector, VoiceprintStore
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry, Services
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.identity import TaggedVoices, VoiceprintStoreContract, speaker_of, tagged


class Muted(TaggedVoices):
    """Tagged voices that cannot make out one speaker (a model failing on them)."""

    async def embed(self, audio: bytes) -> Vector:
        found = speaker_of(audio)
        if found and found[0] == "mute":
            raise ProviderError(self.name, "cannot make this one out", transient=False)
        return await super().embed(audio)


class TaggedSettings(AdapterSettings):
    threshold: float = 0.7


def _build(settings: TaggedSettings, name: str, services: Services) -> TaggedVoices:
    return Muted(threshold=settings.threshold)


TAGGED = Plugin(Family.MODEL, "tagged-voices", TaggedSettings, _build, serves=SpeakerModel)
VARIANT = "models: {voice: {type: speaker, provider: tagged-voices}}\nvoices: {embedder: voice}\n"


def write_wav(path: Path, pcm: bytes, *, rate: int = 16000, channels: int = 1, width: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(pcm)


def household(
    folder: Path,
    voices: Mapping[str, list[str]],
    header: Mapping[str, Any] | None = None,
) -> Path:
    """`voices[folder name]` is whose voice each recording is, in order; the JSONL points at them."""
    for speaker, said in voices.items():
        for n, voice in enumerate(said):
            write_wav(folder / "audio" / speaker / f"{n:02d}.wav", tagged(voice, 2.5, take=n))
    cases = folder / "cases.jsonl"
    record = {"dataset": "speaker-id", "version": 1, "audio": "audio", "spare": 1} | dict(header or {})
    cases.write_text(json.dumps(record) + "\n")
    return cases


def own(speaker: str, count: int = 10) -> list[str]:
    return [speaker] * count


async def bench(folder: Path, cases: Path, text: str = VARIANT, repeat: int = 1) -> Run:
    suite = SpeakerId()
    path = folder / "variant.yaml"
    path.write_text(text)
    variant = load_variant(path, suite, Registry([TAGGED]), EchoLocalizer(), environ={})
    dataset, info = read_dataset(suite, cases)
    (run,) = await run_suite(suite, dataset, info, [variant], Plan(repeat=repeat), Cache(folder / "cache"))
    return run


def values(run: Run) -> dict[str, float | None]:
    return {m.id: m.value for m in run.summary.metrics}


async def test_distinct_voices_are_told_apart_and_impostors_stay_unknown(tmp_path: Path) -> None:
    cases = household(tmp_path, {s: own(s) for s in ("lea", "hugo", "mathis", "jules")}, {"impostors": ["jules"]})
    run = await bench(tmp_path, cases, repeat=2)
    got = values(run)
    assert got["eer"] == 0 and got["far"] == 0 and got["frr"] == 0
    assert got["top1"] == 1 and got["misheard"] == 0 and got["impostors-unknown"] == 1
    assert got["failed-enrollments"] == 0 and got["retakes"] == 0
    assert got["threshold"] == 0.7
    threshold = got["threshold-at-far-1"]
    assert threshold is not None and 0 < threshold < 0.7
    assert got["learned"] and got["learned"] > 0  # clear turns of enrolled voices are learned
    assert got["replay-on-far-last"] == 0  # and learning lets nobody in
    latency, cold = got["latency-p50"], got["cold-start"]
    assert latency is not None and latency >= 0 and cold is not None and cold >= 0
    assert got["model-size"] is None  # a tagged model has no file
    assert run.summary.findings == ()
    assert len(run.results) == 2 * (4 * 4 + 1)  # every everyday turn and the replay, at each repetition


async def test_a_model_that_hears_one_voice_as_another_says_who_was_taken_for_whom(tmp_path: Path) -> None:
    # Hugo's recordings sound like Léa to this model: he is enrolled with her voice, and she is taken for him
    cases = household(tmp_path, {"lea": own("lea"), "hugo": own("lea"), "mathis": own("mathis")})
    run = await bench(tmp_path, cases)
    got = values(run)
    assert got["far"] and got["far"] > 0 and got["top1"] and got["top1"] < 1
    assert got["misheard"] and got["misheard"] > 0
    taken = {(f.detail.args["who"], f.detail.args["whom"]) for f in run.summary.findings}
    assert taken & {("lea", "hugo"), ("hugo", "lea")}
    assert not any("mathis" in pair for pair in taken)


async def test_a_phrase_in_another_voice_is_said_again_and_a_voice_that_never_holds_fails_to_enroll(
    tmp_path: Path,
) -> None:
    lea = ["lea", "hugo", *own("lea", 8)]  # her second phrase was read by Hugo
    mixed = ["mathis", "lea", "hugo", "jules", "zoe", "ines", *own("mathis", 4)]  # never twice the same voice
    cases = household(tmp_path, {"lea": lea, "hugo": own("hugo"), "mathis": mixed})
    got = values(await bench(tmp_path, cases))
    assert got["retakes"] == 1
    assert got["failed-enrollments"] == 1


async def test_turns_without_a_voiceprint_are_counted_and_left_unknown(tmp_path: Path) -> None:
    cases = household(tmp_path, {"lea": own("lea"), "hugo": own("hugo"), "mute": own("mute")}, {"impostors": ["mute"]})
    got = values(await bench(tmp_path, cases))
    assert got["failed"] == 4
    assert got["impostors-unknown"] == 1 and got["eer"] == 0


async def test_without_a_list_one_speaker_in_four_is_an_impostor(tmp_path: Path) -> None:
    speakers = ("a", "b", "c", "d", "e")
    cases = household(tmp_path, {s: own(s) for s in speakers})
    dataset, _ = read_dataset(SpeakerId(), cases)
    assert dataset.shared.impostors == {"d"}
    assert set(dataset.shared.phrases) == {"a", "b", "c", "e"}
    order = [t.speaker for t in dataset.shared.turns]
    assert order[:5] == list(speakers)  # the replay goes round the household


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ({"dataset": "other"}, "bench-speaker-id-no-header"),
        ({"spare": -1}, "bench-speaker-id-no-header"),
        ({"audio": "nowhere"}, "bench-speaker-id-no-audio"),
        ({"impostors": ["zoe"]}, "bench-speaker-id-unknown"),
        ({"spare": 5}, "bench-speaker-id-too-few"),
    ],
)
def test_a_dataset_the_suite_cannot_use_is_refused(tmp_path: Path, header: dict[str, Any], message: str) -> None:
    cases = household(tmp_path, {"lea": own("lea"), "hugo": own("hugo")}, header)
    with pytest.raises(BenchError) as raised:
        read_dataset(SpeakerId(), cases)
    assert raised.value.message.id == message


def test_the_suite_ships_no_recordings(tmp_path: Path) -> None:
    suite = SpeakerId()
    with pytest.raises(BenchError) as raised:
        read_dataset(suite, suite.dataset())
    assert raised.value.message.id == "bench-no-dataset"


def test_a_variant_without_a_voice_model_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text("models: {voice: {type: speaker, provider: tagged-voices}}\n")
    with pytest.raises(BenchError) as raised:
        load_variant(path, SpeakerId(), Registry([TAGGED]), EchoLocalizer(), environ={})
    assert raised.value.message.id == "bench-variant-no-voices"


def test_recordings_in_another_rate_or_in_stereo_are_converted(tmp_path: Path) -> None:
    second = array("h", [1000] * 4000 + [-1000] * 4000)  # one second at 8 kHz: half up, half down
    write_wav(tmp_path / "mono8k.wav", second.tobytes(), rate=8000)
    stereo = array("h", [v for pair in zip([400] * 16000, [200] * 16000, strict=True) for v in pair])
    write_wav(tmp_path / "stereo.wav", stereo.tobytes(), channels=2)
    converted = array("h")
    converted.frombytes(read_pcm(tmp_path / "mono8k.wav"))
    assert len(converted) == 16000 and converted[100] == 1000 and converted[-100] == -1000
    mixed = array("h")
    mixed.frombytes(read_pcm(tmp_path / "stereo.wav"))
    assert len(mixed) == 16000 and set(mixed) == {300}


def test_unreadable_recordings_are_refused(tmp_path: Path) -> None:
    write_wav(tmp_path / "8bit.wav", bytes(1600), width=1)
    (tmp_path / "noise.wav").write_bytes(b"not a wave")
    for name in ("8bit.wav", "noise.wav", "missing.wav"):
        with pytest.raises(BenchError) as raised:
            read_pcm(tmp_path / name)
        assert raised.value.message.id == "bench-speaker-id-bad-audio"


def test_error_rates_and_the_threshold_for_a_target_of_false_accepts() -> None:
    genuine = [0.9, 0.8, 0.7, 0.4]
    impostor = [0.1, 0.2, 0.3, 0.5]
    assert accepted(genuine, 0.7) == 0.75 and accepted([], 0.5) == 0
    assert equal_error_rate(genuine, impostor) == 0.25  # at 0.5: one of four rejected, one of four accepted
    assert equal_error_rate([], impostor) is None
    many = [n / 1000 for n in range(1000)]  # impostor scores 0 to 0.999
    threshold = threshold_for(many, 0.01)
    assert threshold is not None and accepted(many, threshold) <= 0.01 < accepted(many, threshold - 0.002)
    assert threshold_for([], 0.01) is None


class TestMemoryVoiceprints(VoiceprintStoreContract):
    def store(self) -> VoiceprintStore:
        return MemoryVoiceprints()
