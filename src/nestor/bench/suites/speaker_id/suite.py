"""The speaker-id suite: does a voice model tell the household's voices apart, without taking one for another, and
what does it cost on this machine?

Its dataset is a JSONL header pointing at recordings, `<speaker>/<utterance>.wav` under `audio` (relative to the
JSONL file), 16 kHz mono 16-bit (other rates and channels are converted on load):

    {"dataset": "speaker-id", "version": 1, "audio": "data/audio", "spare": 3, "impostors": ["2154", "7601"]}

Each speaker's utterances are taken in name order. For an enrolled speaker, the first ones are the phrases of their
enrollment, as many as the core asks for (`PHRASES`) plus `spare` retakes: they are said through
`Voices.begin/take/finish`, and a phrase the core refuses is said again with the next one. The others are their
everyday turns. Impostors (by default one speaker in four) are never enrolled: their turns must come out unknown.
Every turn is a case, heard by `Voices.hear`.

One more case replays every turn in a fixed order, round after round of the household, through `hear` then
`learn`: what learning changes between the first and the last third of the turns, against the same turns heard
without learning.

Nestor's own `Voices` decides, so what is measured is what runs. The model is measured live, never replayed, one
voiceprint at a time in the process so that latencies are the model's own.
"""

import asyncio
import math
import time
import wave
from array import array
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import percentile
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.suites.speaker_id.store import MemoryVoiceprints, Unlogged
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.identity import PHRASES, SpeakerModel, Vector, Voices, VoiceSpace
from nestor.modules.identity.audio import centroid, similarity
from nestor.modules.journal import Journal

NAME = "speaker-id"
REPLAY = "replay"
ROOMS = ("salon", "cuisine", "chambre")  # where the replayed turns are said, in turn
RATE = 16000
IMPOSTOR_EVERY = 4  # without a list, one speaker in four is never enrolled
FAR_TARGET = 0.01  # the calibration: one pair of different voices in a hundred taken for the same
ENROLLED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Utterance:
    speaker: str
    path: Path


@dataclass(frozen=True, slots=True)
class Household:
    """The recordings: who enrolls with which phrases, and every turn in the order the replay says them."""

    phrases: Mapping[str, tuple[Path, ...]]  # by enrolled speaker, retakes included
    enroll: int
    impostors: frozenset[str]
    turns: tuple[Utterance, ...]


@dataclass(slots=True)
class _Variant:
    """What a variant keeps for the run: its enrolled voices, how enrolling went, the replay once made."""

    voices: Voices
    anchors: dict[PersonId, Vector]
    retakes: int
    failed: tuple[str, ...]
    first_embed_s: float
    replay: dict[str, Any] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SpeakerId(Suite[Household, Knobs]):
    """A variant's `voices` section says which model and threshold: no knobs of its own."""

    name = NAME
    description = "bench-speaker-id-description"
    knobs = Knobs
    models = ()
    voices = True

    def __init__(self) -> None:
        self._variants: dict[str, _Variant] = {}
        self._enrolling: dict[str, asyncio.Lock] = {}
        self._inference = asyncio.Lock()  # one voiceprint at a time in the process: latencies are the model's

    def dataset(self) -> Traversable | None:
        return None  # recordings are too big to ship: `bench/speaker-id/fetch.py` builds a dataset

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[Household]:
        header = records[0] if records else {}
        enroll, spare = len(PHRASES), header.get("spare", 3)
        if (
            header.get("dataset") != NAME
            or not isinstance(header.get("version"), int)
            or not isinstance(header.get("audio"), str)
            or not isinstance(spare, int)
            or spare < 0
        ):
            raise BenchError(Message.of("bench-speaker-id-no-header"))
        folder = Path(str(source)).parent / header["audio"]
        speakers = sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
        if len(speakers) < 2:
            raise BenchError(Message.of("bench-speaker-id-no-audio", path=str(folder)))
        listed = header.get("impostors")
        impostors = frozenset(listed if isinstance(listed, list) else speakers[IMPOSTOR_EVERY - 1 :: IMPOSTOR_EVERY])
        if unknown := impostors - set(speakers):
            raise BenchError(Message.of("bench-speaker-id-unknown", speakers=", ".join(sorted(unknown))))
        phrases: dict[str, tuple[Path, ...]] = {}
        everyday: dict[str, list[Path]] = {}
        for speaker in speakers:
            recorded = sorted((folder / speaker).glob("*.wav"))
            if len(recorded) <= enroll + spare:
                raise BenchError(Message.of("bench-speaker-id-too-few", speaker=speaker, needed=enroll + spare + 1))
            if speaker not in impostors:
                phrases[speaker] = tuple(recorded[: enroll + spare])
            everyday[speaker] = recorded[enroll + spare :]
        rounds = max(map(len, everyday.values()))
        turns = tuple(
            Utterance(speaker, everyday[speaker][n])
            for n in range(rounds)
            for speaker in speakers
            if n < len(everyday[speaker])
        )
        cases = (
            *(Case(id=f"{t.speaker}/{t.path.stem}", data={"speaker": t.speaker, "path": str(t.path)}) for t in turns),
            Case(id=REPLAY, data={}),
        )
        return Dataset(
            version=header["version"],
            cases=cases,
            shared=Household(phrases=phrases, enroll=enroll, impostors=impostors, turns=turns),
        )

    # --- running ------------------------------------------------------------------------------------

    async def run(self, case: Case, shared: Household, trial: Trial[Knobs]) -> Mapping[str, Any]:
        state = await self._variant(shared, trial)
        if case.id == REPLAY:
            return await self._replayed(state, shared, trial)
        audio = await asyncio.to_thread(read_pcm, Path(case.data["path"]))
        async with self._inference:
            clock = time.perf_counter()
            heard = await state.voices.hear(audio)
            latency = time.perf_counter() - clock
        scores = (
            {p: round(similarity(heard.voiceprint, a), 5) for p, a in state.anchors.items()}
            if heard.voiceprint is not None
            else {}
        )
        return {
            "speaker": case.data["speaker"],
            "impostor": case.data["speaker"] in shared.impostors,
            "heard": heard.person,
            "scores": scores,
            "threshold": state.voices.threshold,
            "latency_s": latency,
            "audio_s": heard.duration_s,
            "failed": heard.voiceprint is None,
        }

    async def _variant(self, shared: Household, trial: Trial[Knobs]) -> _Variant:
        """The variant's household, enrolled once through the core's enrollment, phrase checks included."""
        async with self._enrolling.setdefault(trial.variant, asyncio.Lock()):
            if (found := self._variants.get(trial.variant)) is not None:
                return found
            embedder = _voices_of(trial)
            store = MemoryVoiceprints()
            voices = Voices(embedder, store, Journal(Unlogged()), settings=trial.config.voices.settings())
            await voices.start()
            first = await asyncio.to_thread(read_pcm, next(iter(shared.phrases.values()))[0])
            async with self._inference:
                clock = time.perf_counter()
                await embedder.embed(first)  # the first voiceprint after loading: part of a cold start
                first_embed_s = time.perf_counter() - clock
            retakes, failed = 0, []
            for speaker, phrases in shared.phrases.items():
                said = await self._enroll(voices, speaker, phrases, shared.enroll)
                if said is None:
                    failed.append(speaker)
                else:
                    retakes += said - shared.enroll
            profiles = await store.profiles(embedder.space)
            state = _Variant(
                voices=voices,
                anchors={p: centroid(profile.anchor) for p, profile in profiles.items()},
                retakes=retakes,
                failed=tuple(failed),
                first_embed_s=first_embed_s,
            )
            self._variants[trial.variant] = state
            return state

    async def _enroll(self, voices: Voices, speaker: str, phrases: tuple[Path, ...], needed: int) -> int | None:
        """Say the phrases until the core keeps `needed` of them; how many were said, None when they ran out."""
        enrollment = voices.begin(PersonId(speaker), by=None, where=f"bench:{speaker}")
        for said, path in enumerate(phrases, start=1):
            phrase = enrollment.next
            assert phrase is not None  # the enrollment is not complete yet
            audio = await asyncio.to_thread(read_pcm, path)
            async with self._inference:
                check = await voices.take(enrollment.id, phrase, audio)
            if check.complete:
                await voices.finish(enrollment.id)
                return said
        voices.abandon(enrollment.id)
        return None

    async def _replayed(self, state: _Variant, shared: Household, trial: Trial[Knobs]) -> dict[str, Any]:
        """Every turn in order, heard with and without learning; made once per variant (voiceprints do not change
        from one repetition to the next), with how starting the model went."""
        async with state.lock:
            if state.replay is None:
                state.replay = await self._replay(state, shared, trial)
        return state.replay

    async def _replay(self, state: _Variant, shared: Household, trial: Trial[Knobs]) -> dict[str, Any]:
        embedder = _voices_of(trial)
        remembered = _Remembered(embedder, self._inference)
        settings = trial.config.voices.settings()
        heard_by: dict[bool, Voices] = {}
        for learning in (False, True):
            store = MemoryVoiceprints()
            for person, profile in (await state.voices.store.profiles(embedder.space)).items():
                await store.enroll(person, embedder.space, profile.anchor, learning=learning, at=ENROLLED_AT)
            heard_by[learning] = Voices(remembered, store, Journal(Unlogged()), settings=settings)
            await heard_by[learning].start()
        turns: list[list[Any]] = []
        learned = 0
        for n, turn in enumerate(shared.turns):
            audio = await asyncio.to_thread(read_pcm, turn.path)
            without = await heard_by[False].hear(audio)
            heard = await heard_by[True].hear(audio)
            learned += await heard_by[True].learn(heard, turn=f"t{n}", room=ROOMS[n % len(ROOMS)])
            turns.append([turn.speaker, turn.speaker in shared.impostors, without.person, heard.person])
        started = trial.voices_started
        details = embedder.details()
        model_file = Path(details["file"]) if "file" in details else None
        return {
            "turns": turns,
            "learned": learned,
            "retakes": state.retakes,
            "failed_enrollments": list(state.failed),
            "cold_start_s": started.seconds + state.first_embed_s if started else None,
            "memory_bytes": started.memory_bytes if started else None,
            "model_bytes": model_file.stat().st_size if model_file and model_file.is_file() else None,
        }

    # --- scoring ------------------------------------------------------------------------------------

    def summarise(self, dataset: Dataset[Household], results: Sequence[CaseResult]) -> Summary:
        turns = [r.output for r in results if r.case != REPLAY]
        replays = [r.output for r in results if r.case == REPLAY]
        genuine: list[float] = []
        impostor: list[float] = []
        top1 = known = misheard = impostors = impostors_unknown = unrecognised = failed = 0
        taken: Counter[tuple[str, str]] = Counter()
        highest: dict[tuple[str, str], float] = {}
        for out in turns:
            speaker, scores, heard = out["speaker"], out["scores"], out["heard"]
            failed += out["failed"]
            for person, score in scores.items():
                (genuine if person == speaker else impostor).append(score)
            if heard is not None and heard != speaker:
                misheard += 1
                taken[speaker, heard] += 1
                highest[speaker, heard] = max(highest.get((speaker, heard), -1.0), scores.get(heard, -1.0))
            if out["impostor"]:
                impostors += 1
                impostors_unknown += heard is None
            elif speaker in scores:
                known += 1
                top1 += max(scores, key=lambda p: scores[p]) == speaker
                unrecognised += heard is None
        threshold = turns[0]["threshold"] if turns else None
        latencies = [o["latency_s"] for o in turns if not o["failed"]]
        factors = [o["latency_s"] / o["audio_s"] for o in turns if not o["failed"] and o["audio_s"]]
        calibrated = threshold_for(impostor, FAR_TARGET)
        replay = replays[0] if replays else None

        def metric(id: str, value: float | None, unit: Unit, better: Better = Better.LOWER) -> Metric:
            return Metric(id=id, label=f"bench-speaker-id-{id}", value=value, unit=unit, better=better)

        precision = (
            metric("eer", equal_error_rate(genuine, impostor), Unit.RATIO),
            metric("threshold", threshold, Unit.RATIO, Better.NEITHER),
            metric("far", None if threshold is None else accepted(impostor, threshold), Unit.RATIO),
            metric("frr", None if threshold is None else 1 - accepted(genuine, threshold), Unit.RATIO),
            metric("threshold-at-far-1", calibrated, Unit.RATIO, Better.NEITHER),
            metric("frr-at-far-1", None if calibrated is None else 1 - accepted(genuine, calibrated), Unit.RATIO),
            metric("top1", _ratio(top1, known), Unit.RATIO, Better.HIGHER),
            metric("unrecognised", _ratio(unrecognised, known), Unit.RATIO),
            metric("misheard", _ratio(misheard, len(turns)), Unit.RATIO),
            metric("impostors-unknown", _ratio(impostors_unknown, impostors), Unit.RATIO, Better.HIGHER),
            metric("failed", failed, Unit.COUNT),
        )
        learning = _learning(replay, metric) if replay else ()
        compute = (
            metric("cold-start", replay["cold_start_s"] if replay else None, Unit.DURATION),
            metric("latency-p50", percentile(latencies, 0.5), Unit.DURATION),
            metric("latency-p95", percentile(latencies, 0.95), Unit.DURATION),
            metric("rtf-p50", percentile(factors, 0.5), Unit.RATIO),
            metric("model-size", replay["model_bytes"] if replay else None, Unit.BYTES),
            metric("memory", replay["memory_bytes"] if replay else None, Unit.BYTES),
        )
        repetitions = len({r.repetition for r in results}) or 1
        findings = tuple(
            Finding(
                group="bench-speaker-id-taken-list",
                case=f"{who}>{whom}",
                detail=Message.of(
                    "bench-speaker-id-taken",
                    who=who,
                    whom=whom,
                    times=times // repetitions,
                    score=f"{highest[who, whom]:.2f}",
                ),
            )
            for (who, whom), times in sorted(taken.items(), key=lambda item: (-item[1], item[0]))
        )
        return Summary(metrics=(*precision, *learning, *compute), findings=findings)


def _learning(replay: Mapping[str, Any], metric: Callable[[str, float | None, Unit], Metric]) -> tuple[Metric, ...]:
    """False accepts and rejects over the first and the last third of the replayed turns, without and with
    learning: what a household's weeks of turns teach, and whether it lets other voices in."""
    turns = replay["turns"]
    third = len(turns) // 3
    parts = {"first": turns[:third], "last": turns[len(turns) - third :]}
    found: list[Metric] = []
    for learning, column in (("off", 2), ("on", 3)):
        for part, chosen in parts.items():
            wrong = sum(1 for t in chosen if t[column] is not None and t[column] != t[0])
            known = [t for t in chosen if not t[1]]
            missed = sum(1 for t in known if t[column] != t[0])
            found.append(metric(f"replay-{learning}-far-{part}", _ratio(wrong, len(chosen)), Unit.RATIO))
            found.append(metric(f"replay-{learning}-frr-{part}", _ratio(missed, len(known)), Unit.RATIO))
    found.append(metric("learned", replay["learned"], Unit.COUNT))
    found.append(metric("retakes", replay["retakes"], Unit.COUNT))
    found.append(metric("failed-enrollments", len(replay["failed_enrollments"]), Unit.COUNT))
    return tuple(found)


def _voices_of(trial: Trial[Knobs]) -> SpeakerModel:
    if trial.voices is None:  # pragma: no cover - the engine gives it: the suite declares `voices`
        raise BenchError(Message.of("bench-variant-no-voices", path=trial.variant))
    return trial.voices


class _Remembered(SpeakerModel):
    """The variant's model, embedding the turn being replayed once for both households (with and without
    learning), one voiceprint at a time."""

    name = "remembered-voices"

    def __init__(self, model: SpeakerModel, inference: asyncio.Lock) -> None:
        self.model, self.inference = model, inference
        self.sample_rate = model.sample_rate
        self._last: tuple[bytes, Vector] | None = None

    @property
    def space(self) -> VoiceSpace:
        return self.model.space

    @property
    def threshold(self) -> float:
        return self.model.threshold

    async def embed(self, audio: bytes) -> Vector:
        if self._last is not None and self._last[0] is audio:
            return self._last[1]
        async with self.inference:
            voiceprint = await self.model.embed(audio)
        self._last = (audio, voiceprint)
        return voiceprint


# --- measures -------------------------------------------------------------------------------------


def accepted(scores: Sequence[float], threshold: float) -> float:
    """The share of scores at or above the threshold (0 without scores)."""
    return sum(1 for s in scores if s >= threshold) / len(scores) if scores else 0.0


def equal_error_rate(genuine: Sequence[float], impostor: Sequence[float]) -> float | None:
    """The error where false accepts and false rejects are equal, at the threshold that brings them closest."""
    if not genuine or not impostor:
        return None
    ordered_genuine, ordered_impostor = sorted(genuine), sorted(impostor)
    best: tuple[float, float] | None = None
    for threshold in sorted({*genuine, *impostor}):
        rejected = bisect_left(ordered_genuine, threshold) / len(genuine)
        accepts = 1 - bisect_left(ordered_impostor, threshold) / len(impostor)
        gap = abs(accepts - rejected)
        if best is None or gap < best[0]:
            best = (gap, (accepts + rejected) / 2)
    assert best is not None
    return best[1]


def threshold_for(impostor: Sequence[float], far: float) -> float | None:
    """The lowest threshold, to a thousandth, at which at most `far` of the impostor pairs are accepted."""
    if not impostor:
        return None
    allowed = math.floor(far * len(impostor))
    ordered = sorted(impostor, reverse=True)
    above = ordered[allowed] if allowed < len(ordered) else ordered[-1]
    return math.floor(above * 1000) / 1000 + 0.001


def _ratio(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def read_pcm(path: Path) -> bytes:
    """A WAV file as 16 kHz mono 16-bit PCM, its channels averaged and its rate converted when it differs."""
    try:
        with wave.open(str(path), "rb") as source:
            channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
            frames = source.readframes(source.getnframes())
    except (OSError, wave.Error, EOFError):
        raise BenchError(Message.of("bench-speaker-id-bad-audio", path=str(path))) from None
    if width != 2:
        raise BenchError(Message.of("bench-speaker-id-bad-audio", path=str(path)))
    pcm = array("h")
    pcm.frombytes(frames)
    if channels > 1:
        pcm = array("h", (sum(pcm[i : i + channels]) // channels for i in range(0, len(pcm), channels)))
    if rate != RATE:
        pcm = _resampled(pcm, rate)
    return pcm.tobytes()


def _resampled(pcm: array, rate: int) -> array:
    """Linear interpolation to 16 kHz: enough for a voiceprint, which keeps nothing above 8 kHz."""
    count = int(len(pcm) * RATE / rate)
    step = rate / RATE
    out = array("h", bytes(2 * count))
    for n in range(count):
        position = n * step
        low = int(position)
        high = min(low + 1, len(pcm) - 1)
        out[n] = round(pcm[low] + (pcm[high] - pcm[low]) * (position - low))
    return out
