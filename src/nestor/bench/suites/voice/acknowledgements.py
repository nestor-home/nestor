"""The `acknowledgements` bench: what a person says while the assistant speaks, recorded by the variant's speech model
then heard by its transcription model, as on a satellite. Each case is either an acknowledgement ("mm-hmm", "ouais"),
which must not cut the assistant off, or a real reply ("wait", "attends"), which must.

Measured: the share of acknowledgements let through and of replies that cut it off, both on what was heard and on
what was written (the second isolates the word list from the ear). The judge decides with the satellites' own rule
(`is_acknowledgement`). A long reply also cuts off by its length on a satellite; the bench only measures the words."""

from collections.abc import Mapping, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.adapters.channels.satellites.voice.acknowledgements import is_acknowledgement
from nestor.bench.errors import BenchError
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import ProviderError
from nestor.core.i18n import Message

NAME = "acknowledgements"
RECORDING = "audio/ogg"  # what `SpeechModel.synthesize` records
KINDS = ("acknowledgement", "reply")


class Acknowledgements(Suite[None, Knobs]):
    name = NAME
    description = "bench-ack-description"
    knobs = Knobs
    models = ()
    transcription = True
    speech = True

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "acknowledgements.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[None]:
        header = records[0] if records else {}
        if header.get("dataset") != NAME or not isinstance(header.get("version"), int):
            raise BenchError(Message.of("bench-ack-no-header"))
        cases = []
        for record in records[1:]:
            if not (isinstance(record.get("text"), str) and record.get("kind") in KINDS):
                raise BenchError(Message.of("bench-ack-bad-case", case=str(record.get("id", "?"))))
            cases.append(
                Case(
                    id=str(record["id"]),
                    data={"text": record["text"], "kind": record["kind"], "language": record.get("language", "")},
                )
            )
        return Dataset(version=header["version"], cases=tuple(cases), shared=None)

    async def run(self, case: Case, shared: None, trial: Trial[Knobs]) -> Mapping[str, Any]:
        voice, ear = trial.speech, trial.transcription
        assert voice is not None and ear is not None  # the engine gives them to a suite that asks for them
        text = case.data["text"]
        out: dict[str, Any] = {"written": is_acknowledgement(text)}
        try:
            heard = await ear.transcribe(await voice.synthesize(text), RECORDING)
        except ProviderError as error:
            return out | {"failed": str(error)}
        return out | {"heard": heard, "judged": is_acknowledgement(heard)}

    def summarise(self, dataset: Dataset[None], results: Sequence[CaseResult]) -> Summary:
        kind = {c.id: c.data["kind"] for c in dataset.cases}
        said = {c.id: c.data["text"] for c in dataset.cases}
        heard = [r for r in results if "judged" in r.output]

        def share(rs: Sequence[CaseResult], of: str, field: str, value: bool) -> float | None:
            mine = [r for r in rs if kind[r.case] == of]
            return sum(r.output[field] is value for r in mine) / len(mine) if mine else None

        def metric(id: str, value: float | None, unit: Unit = Unit.RATIO, better: Better = Better.HIGHER) -> Metric:
            return Metric(id=id, label=f"bench-ack-{id}", value=value, unit=unit, better=better)

        def wrong(r: CaseResult) -> bool:
            return r.output["judged"] is (kind[r.case] == "reply")

        return Summary(
            metrics=(
                metric("let-through", share(heard, "acknowledgement", "judged", True)),
                metric("cut-off", share(heard, "reply", "judged", False)),
                metric("let-through-written", share(results, "acknowledgement", "written", True)),
                metric("cut-off-written", share(results, "reply", "written", False)),
                metric("failed", len(results) - len(heard), Unit.COUNT, Better.LOWER),
            ),
            findings=tuple(
                Finding(
                    group=f"bench-ack-wrong-{kind[r.case]}",
                    case=r.case,
                    detail=Message.of("bench-ack-heard", said=said[r.case], heard=r.output["heard"]),
                )
                for r in heard
                if wrong(r)
            ),
        )
