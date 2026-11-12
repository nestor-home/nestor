"""The `speech` bench: everyday sentences recorded by the variant's speech model, as an answer to a voice message is
(`synthesize`, the whole sentence at once), then heard back by the variant's transcription model, the judge.

Measured: the latency of a sentence, and how clearly it is spoken: the word error rate of the judge on it, a number
heard back in figures counting as said (a case lists those ways in `also`). Keep the same judge across variants (a
local model, `sherpa-onnx` Parakeet): what it misses on a voice it would hear clearly elsewhere is the voice's. The
satellites' live voice is not measured here."""

import time
from collections.abc import Mapping, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import percentile
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.suites.voice.words import errors, words
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import ProviderError
from nestor.core.i18n import Message

NAME = "speech"
RECORDING = "audio/ogg"  # what `SpeechModel.synthesize` records


class Speech(Suite[None, Knobs]):
    name = NAME
    description = "bench-speech-description"
    knobs = Knobs
    models = ()
    transcription = True  # the judge
    speech = True

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "sentences.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[None]:
        header = records[0] if records else {}
        if header.get("dataset") != NAME or not isinstance(header.get("version"), int):
            raise BenchError(Message.of("bench-speech-no-header"))
        cases = []
        for record in records[1:]:
            if not isinstance(record.get("text"), str):
                raise BenchError(Message.of("bench-speech-bad-case", case=str(record.get("id", "?"))))
            also = record.get("also", [])
            cases.append(Case(id=str(record["id"]), data={"text": record["text"], "also": list(also)}))
        return Dataset(version=header["version"], cases=tuple(cases), shared=None)

    async def run(self, case: Case, shared: None, trial: Trial[Knobs]) -> Mapping[str, Any]:
        voice, judge = trial.speech, trial.transcription
        assert voice is not None and judge is not None  # the engine gives them to a suite that asks for them
        text = case.data["text"]
        started = trial.started.get(NAME)
        out: dict[str, Any] = {"words": len(words(text)), "cold_start_s": started.seconds if started else None}
        clock = time.perf_counter()
        try:
            audio = await voice.synthesize(text)
        except ProviderError as error:
            return out | {"failed": str(error)}
        out["latency_s"] = time.perf_counter() - clock
        try:
            heard = await judge.transcribe(audio, RECORDING)
        except ProviderError as error:
            return out | {"unheard": str(error)}
        said = (text, *case.data["also"])  # a number heard back in figures was said all the same
        return out | {"heard": heard, "errors": min(errors(way, heard) for way in said)}

    def summarise(self, dataset: Dataset[None], results: Sequence[CaseResult]) -> Summary:
        spoken = [r for r in results if "failed" not in r.output]
        heard = [r for r in spoken if "heard" in r.output]
        said = {c.id: c.data["text"] for c in dataset.cases}
        latencies = [r.output["latency_s"] for r in spoken]
        total = sum(r.output["words"] for r in heard)
        first = results[0].output if results else {}

        def metric(id: str, value: float | None, unit: Unit, better: Better = Better.LOWER) -> Metric:
            return Metric(id=id, label=f"bench-speech-{id}", value=value, unit=unit, better=better)

        return Summary(
            metrics=(
                metric("wer", sum(r.output["errors"] for r in heard) / total if total else None, Unit.RATIO),
                metric("failed", len(results) - len(spoken), Unit.COUNT),
                metric("unheard", len(spoken) - len(heard), Unit.COUNT),
                metric("latency-p50", percentile(latencies, 0.5), Unit.DURATION),
                metric("latency-p95", percentile(latencies, 0.95), Unit.DURATION),
                metric("cold-start", first.get("cold_start_s"), Unit.DURATION),
            ),
            findings=tuple(
                Finding(
                    group="bench-speech-misheard",
                    case=r.case,
                    detail=Message.of("bench-speech-heard", said=said[r.case], heard=r.output["heard"]),
                )
                for r in heard
                if r.output["errors"]
            ),
        )
