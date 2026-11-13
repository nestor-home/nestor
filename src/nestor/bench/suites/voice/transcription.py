"""The `transcription` bench: recordings of read French (Multilingual LibriSpeech, CC BY 4.0) heard by the variant's
transcription model, as a voice message is (`transcribe`, the whole recording at once).

Measured: the word error rate over all the words, the recordings it failed on, the latency and the real-time factor
(seconds of work per second of speech) of each recording, and the cold start (loading a local model). One recording
at a time by default: the latency is the model's alone. The satellites' live voice is not measured here: a provider
whose realtime model differs from its file model (ElevenLabs) is measured on the file one."""

import asyncio
import time
from collections.abc import Mapping, Sequence
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import percentile
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.suites.voice.words import errors, rate, words
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import ProviderError
from nestor.core.i18n import Message

NAME = "transcription"
WORST = 10  # recordings shown as findings


class Transcription(Suite[None, Knobs]):
    name = NAME
    description = "bench-transcription-description"
    knobs = Knobs
    models = ()
    transcription = True

    def dataset(self) -> Traversable | None:
        return None  # recordings too big for the package: `bench/voice/fetch.py` writes them and `cases.jsonl`

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[None]:
        header = records[0] if records else {}
        if header.get("dataset") != NAME or not isinstance(header.get("version"), int):
            raise BenchError(Message.of("bench-transcription-no-header"))
        folder = Path(str(source)).parent / str(header.get("audio", "."))
        cases = []
        for record in records[1:]:
            path = folder / str(record.get("file", ""))
            if not (isinstance(record.get("text"), str) and path.is_file()):
                raise BenchError(Message.of("bench-transcription-bad-case", case=str(record.get("id", "?"))))
            cases.append(
                Case(
                    id=str(record["id"]), data={"path": str(path), "text": record["text"], "seconds": record["seconds"]}
                )
            )
        return Dataset(version=header["version"], cases=tuple(cases), shared=None)

    async def run(self, case: Case, shared: None, trial: Trial[Knobs]) -> Mapping[str, Any]:
        model = trial.transcription
        assert model is not None  # the engine gives one to a suite that asks for it
        audio = await asyncio.to_thread(Path(case.data["path"]).read_bytes)
        started = trial.started.get("transcription")
        out: dict[str, Any] = {
            "seconds": case.data["seconds"],
            "words": len(words(case.data["text"])),
            "cold_start_s": started.seconds if started else None,
            "memory_bytes": started.memory_bytes if started else None,
        }
        clock = time.perf_counter()
        try:
            heard = await model.transcribe(audio, "audio/wav")
        except ProviderError as error:
            return out | {"failed": str(error)}
        return out | {
            "heard": heard,
            "errors": errors(case.data["text"], heard),
            "latency_s": time.perf_counter() - clock,
        }

    def summarise(self, dataset: Dataset[None], results: Sequence[CaseResult]) -> Summary:
        heard = [r for r in results if "failed" not in r.output]
        said = {c.id: c.data["text"] for c in dataset.cases}
        latencies = [r.output["latency_s"] for r in heard]
        factors = [r.output["latency_s"] / r.output["seconds"] for r in heard if r.output["seconds"]]
        first = results[0].output if results else {}

        def metric(id: str, value: float | None, unit: Unit, better: Better = Better.LOWER) -> Metric:
            return Metric(id=id, label=f"bench-transcription-{id}", value=value, unit=unit, better=better)

        worst = sorted(heard, key=lambda r: -r.output["errors"] / max(r.output["words"], 1))[:WORST]
        return Summary(
            metrics=(
                metric("wer", rate(r.output for r in heard), Unit.RATIO),
                metric("failed", len(results) - len(heard), Unit.COUNT),
                metric("latency-p50", percentile(latencies, 0.5), Unit.DURATION),
                metric("latency-p95", percentile(latencies, 0.95), Unit.DURATION),
                metric("rtf-p50", percentile(factors, 0.5), Unit.RATIO),
                metric("cold-start", first.get("cold_start_s"), Unit.DURATION),
                metric("memory", first.get("memory_bytes"), Unit.BYTES),
            ),
            findings=tuple(
                Finding(
                    group="bench-transcription-worst",
                    case=r.case,
                    detail=Message.of("bench-transcription-heard", said=said[r.case], heard=r.output["heard"]),
                )
                for r in worst
                if r.output["errors"]
            ),
        )
