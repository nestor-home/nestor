"""The suite port: what a benchmark measures. Suites are plugins, declared like adapters:

    [project.entry-points."nestor.benches"]
    watch-triage = "nestor.bench.suites.watch_triage:suite"

The engine reads the dataset, builds the variant's models, runs every case against every variant and
repetition, records each model call and writes the results; a suite only says what a case is, how to run
one and how to score the lot.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from typing import Any

from pydantic import BaseModel, ConfigDict

from nestor.bench.types import Case, CaseResult, Dataset, Summary
from nestor.core import ContractError
from nestor.modules.cognition import ConversationModel
from nestor.modules.cognition.embedding import Embedder
from nestor.runtime.config import NestorConfig
from nestor.runtime.plugins import Plugin


class Knobs(BaseModel):
    """The `bench` section of a variant: its name, and the suite's own settings (a subclass adds them)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str | None = None  # default: the variant file's name


@dataclass(frozen=True, slots=True, kw_only=True)
class Trial[K: Knobs]:
    """One variant at one repetition: what a suite runs a case with."""

    variant: str
    knobs: K
    config: NestorConfig  # the variant's fragment over the defaults of a configuration
    models: Mapping[str, ConversationModel]  # by role, measured and cached by the engine
    repetition: int
    seed: int
    embedder: Embedder | None = None  # the variant's `memory.embedder`, started, when the suite asks for it

    def model(self, role: str) -> ConversationModel:
        try:
            return self.models[role]
        except KeyError:
            raise ContractError(f"the suite asked for the model {role!r} it did not declare") from None


class Suite[S, K: Knobs](ABC):
    """A benchmark.

    Contract:
    - `load` turns the JSONL records into cases, refusing a dataset it cannot read with a `ContractError`;
    - `run` answers one case with a JSON-serialisable output, using only the trial's models (so every call
      is measured and can be replayed) and handling provider errors the way the measured code does;
    - `summarise` scores the outputs against the expected answers, whatever their order.
    """

    name: str  # the command line's: "watch-triage"
    description: str  # a message id
    knobs: type[K]
    models: tuple[str, ...] = ("written",)  # the roles whose models it calls (`NestorConfig.roles`)
    embedder: bool = False  # it searches by meaning with the variant's `memory.embedder`, when there is one
    plugins: tuple[Plugin[Any], ...] = ()  # extra model kinds for variants (a deterministic fake for CI)

    @abstractmethod
    def dataset(self) -> Traversable:
        """The JSONL dataset shipped with the suite."""

    @abstractmethod
    def load(self, records: Sequence[Mapping[str, Any]]) -> Dataset[S]: ...

    @abstractmethod
    async def run(self, case: Case, shared: S, trial: Trial[K]) -> Mapping[str, Any]: ...

    @abstractmethod
    def summarise(self, dataset: Dataset[S], results: Sequence[CaseResult]) -> Summary: ...
