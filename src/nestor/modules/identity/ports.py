"""Ports of speaker identity: a model that turns a voice into a voiceprint, and where voiceprints are kept. Comparing
voices, learning them and forgetting them is the core's (`Voices`), the same for every model."""

from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from nestor.core import Component, PersonId
from nestor.modules.identity.types import Learned, Profile, Vector, VoiceSpace


class VoiceEmbedder(Component, ABC):
    """Turns speech into a voiceprint of its `space`: a model plugged under `models`, chosen on the `speaker-id`
    bench.

    Contract (checked by `nestor.testing.identity.VoiceEmbedderContract`):
    - `embed` takes 16-bit little-endian mono PCM at `sample_rate` and returns one vector of `space.dimensions`;
      two utterances of one voice are closer (cosine) than two voices;
    - the work runs off the event loop: a turn waits for it while the transcription runs;
    - `threshold` is the cosine similarity from which two voiceprints are the same voice, as calibrated on the
      bench for this model (the configuration may override it);
    - a model that cannot run raises `ProviderError`, never a vendor exception.
    """

    sample_rate: int = 16000

    @property
    @abstractmethod
    def space(self) -> VoiceSpace: ...

    @property
    @abstractmethod
    def threshold(self) -> float: ...

    @abstractmethod
    async def embed(self, audio: bytes) -> Vector: ...


class VoiceprintStore(Component, ABC):
    """People's voices, kept apart from the journal so that forgetting one really erases it.

    Contract (checked by `nestor.testing.identity.VoiceprintStoreContract`):
    - `profiles` reads every person enrolled in a space; a person has one profile, in one space;
    - `enroll` replaces the person's profile (anchor and what was learned) with a new anchor;
    - `learn` adds a learned voiceprint, then drops the oldest beyond `keep`, and beyond `per_room` in its room;
    - `unlearn` removes what was learned from the given turns, wherever it is, and says whose voices changed;
    - `forget` erases a person's voice, or only what was learned;
    - `keep_only` erases every profile of another space (the model changed);
    - `keep_people` erases the voice of everyone else, whatever its space, and says whose.
    """

    @abstractmethod
    async def profiles(self, space: VoiceSpace) -> Mapping[PersonId, Profile]: ...

    @abstractmethod
    async def enroll(
        self, person: PersonId, space: VoiceSpace, anchor: Sequence[Vector], *, learning: bool, at: datetime
    ) -> None: ...

    @abstractmethod
    async def learn(self, person: PersonId, sample: Learned, *, keep: int, per_room: int) -> None: ...

    @abstractmethod
    async def unlearn(self, turns: Collection[str]) -> frozenset[PersonId]: ...

    @abstractmethod
    async def set_learning(self, person: PersonId, learning: bool) -> None: ...

    @abstractmethod
    async def forget(self, person: PersonId, *, learned_only: bool = False) -> None: ...

    @abstractmethod
    async def keep_only(self, space: VoiceSpace) -> None: ...

    @abstractmethod
    async def keep_people(self, people: Collection[PersonId]) -> frozenset[PersonId]: ...
