"""The voice benches on scripted models (nothing to download, no key): word error rate as speech recognition
counts it, recordings heard or failed, sentences recorded and heard back by the judge."""

import json
from pathlib import Path

import pytest

from nestor.bench import BenchError
from nestor.bench.recording import Cache
from nestor.bench.results import Run
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.suites.voice import Speech, Transcription
from nestor.bench.suites.voice.words import errors
from nestor.bench.variants import load_variant
from nestor.core import ProviderError
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry
from nestor.testing.channels import OGG, ScriptedSpeech
from nestor.testing.i18n import EchoLocalizer


class Ears(TranscriptionModel):
    """Hears the text a recording carries (after the `OGG` mark, for a recorded answer); fails on "panne"."""

    name = "ears"

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        text = audio.removeprefix(OGG).decode()
        if "panne" in text:
            raise ProviderError(self.name, "overloaded", transient=True)
        return text.strip()


EARS_PLUGIN = Plugin(Family.MODEL, "ears", AdapterSettings, lambda s, n, x: Ears(), serves=TranscriptionModel)
VOICE_PLUGIN = Plugin(Family.MODEL, "voice", AdapterSettings, lambda s, n, x: ScriptedSpeech(), serves=SpeechModel)
PLUGINS = Registry([EARS_PLUGIN, VOICE_PLUGIN])
EARS = "  ears: {type: transcription, provider: ears}\n"
VOICE = "  voice: {type: speech, provider: voice}\n"


async def bench(folder: Path, suite: Transcription | Speech, models: str, cases: Path | None = None) -> Run:
    path = folder / "variant.yaml"
    path.write_text("models:\n" + models)
    variant = load_variant(path, suite, PLUGINS, EchoLocalizer(), environ={})
    dataset, info = read_dataset(suite, cases or suite.dataset())
    (run,) = await run_suite(suite, dataset, info, [variant], Plan(), Cache(folder / "cache"))
    return run


@pytest.mark.parametrize(
    ("said", "heard", "count"),
    [
        ("Rappelle-moi d'acheter du pain.", "rappelle moi d'acheter du pain", 0),  # case and punctuation
        ("allume la lumière du salon", "allume la lumiere du salon", 1),  # an accent tells words apart
        ("il fait douze degrés", "il fait 12 degrés", 1),  # figures for letters
        ("éteins la cuisine", "éteins cuisine", 1),  # a word missed
        ("bonjour", "bonjour bonjour toi", 2),  # words added
    ],
)
def test_word_errors_count_what_recognition_gets_wrong(said: str, heard: str, count: int) -> None:
    assert errors(said, heard) == count


async def test_recordings_are_scored_on_their_words_and_failures_counted_apart(tmp_path: Path) -> None:
    recordings = {
        "r1": ("le dîner est prêt", "le dîner est prêt"),
        "r2": ("ferme la porte du garage", "ferme la porte"),
        "r3": ("la panne", "ignored"),
    }
    (tmp_path / "audio").mkdir()
    lines = [{"dataset": "transcription", "version": 1, "audio": "audio"}]
    for case, (heard, said) in recordings.items():
        (tmp_path / "audio" / f"{case}.wav").write_text(heard)
        lines.append({"id": case, "file": f"{case}.wav", "text": said, "seconds": 2.0})
    cases = tmp_path / "cases.jsonl"
    cases.write_text("".join(json.dumps(line) + "\n" for line in lines))

    run = await bench(tmp_path, Transcription(), EARS, cases)

    got = {m.id: m.value for m in run.summary.metrics}
    assert got["wer"] == 2 / 7, "two words added to the seven said, the failed recording left out"
    assert got["failed"] == 1
    assert [f.case for f in run.summary.findings] == ["r2"]


async def test_sentences_are_recorded_then_heard_back_by_the_judge(tmp_path: Path) -> None:
    run = await bench(tmp_path, Speech(), EARS + VOICE)
    got = {m.id: m.value for m in run.summary.metrics}
    assert len(run.results) == 20, "the sentences shipped with the suite"
    assert (got["wer"], got["failed"], got["unheard"]) == (0, 0, 0)
    assert run.summary.findings == ()


async def test_a_variant_without_the_models_a_suite_needs_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BenchError) as refused:
        await bench(tmp_path, Speech(), EARS)
    assert refused.value.message.id == "bench-variant-no-speech"


class InFigures(Ears):
    """A judge that writes numbers in figures, as recognition models do."""

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        return (await super().transcribe(audio, media_type)).replace("douze", "12")


async def test_a_number_heard_back_in_figures_counts_as_said(tmp_path: Path) -> None:
    cases = tmp_path / "sentences.jsonl"
    header = {"dataset": "speech", "version": 1}
    said = {"id": "s1", "text": "Il fait douze degrés.", "also": ["Il fait 12 degrés."]}
    cases.write_text(f"{json.dumps(header)}\n{json.dumps(said)}\n")
    figures = Plugin(Family.MODEL, "figures", AdapterSettings, lambda s, n, x: InFigures(), serves=TranscriptionModel)
    registry = Registry([figures, VOICE_PLUGIN])
    path = tmp_path / "variant.yaml"
    path.write_text("models:\n  ears: {type: transcription, provider: figures}\n" + VOICE)
    variant = load_variant(path, Speech(), registry, EchoLocalizer(), environ={})
    dataset, info = read_dataset(Speech(), cases)
    (run,) = await run_suite(Speech(), dataset, info, [variant], Plan(), Cache(tmp_path / "cache"))
    assert {m.id: m.value for m in run.summary.metrics}["wer"] == 0
