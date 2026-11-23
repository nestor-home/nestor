"""Models that count their calls: each model of `models` is used through one of these, whatever its type, so that
every call reaches the ledger the same way. A wrapper changes nothing to what the caller sees: it is a model of the
same type, with the same capabilities, and leaves starting and closing the model to whoever owns it."""

from collections.abc import AsyncGenerator, Generator, Mapping, Sequence
from contextlib import aclosing, contextmanager

from nestor.core import ContractError, Health, Model, counted, counting
from nestor.core.i18n import Message as Phrase
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.modules.cognition.embedding import EmbeddingModel, EmbeddingSpace, Vector
from nestor.modules.cognition.images import ImageModel
from nestor.modules.cognition.model import Image, LanguageModel, ModelOutput, ModelRequest
from nestor.modules.identity import SpeakerModel, VoiceSpace
from nestor.modules.identity import Vector as Voiceprint
from nestor.modules.usage.attribution import attribution
from nestor.modules.usage.meter import Meter
from nestor.modules.usage.types import Attribution, Consumer


class Counted[M: Model]:
    """What every counting wrapper shares: the model it counts, which names, describes and reports its health, and
    one call measured at a time."""

    def __init__(self, model: M, consumer: Consumer, meter: Meter) -> None:
        self.model, self.consumer, self.meter = model, consumer, meter
        if isinstance(self, Model):  # every counted model is also one of its type (`CountedLanguage`…)
            self.mirror(model)

    @contextmanager
    def counting(self) -> Generator[None]:
        """A call made within the block, measured on behalf of the work in progress."""
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            yield

    def health(self) -> Health:
        return self.model.health()

    def health_detail(self) -> Phrase | None:
        return self.model.health_detail()

    def notes(self) -> Sequence[str]:
        return self.model.notes()

    def details(self) -> Mapping[str, str]:
        return self.model.details()


class CountedLanguage(Counted[LanguageModel], LanguageModel):
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        return self._stream(request, attribution())  # on behalf of whoever asks, whoever reads

    async def _stream(self, request: ModelRequest, said: Attribution) -> AsyncGenerator[ModelOutput]:
        with self.meter.measure(self.consumer, said) as call:
            # closed with the call, cut or not: what the provider billed is reported before the call is recorded
            async with aclosing(counted(self.model.stream(request), call.tally)) as outputs:
                async for output in outputs:
                    yield output


class CountedEmbedding(Counted[EmbeddingModel], EmbeddingModel):
    @property
    def space(self) -> EmbeddingSpace:
        return self.model.space

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        with self.counting():
            return await self.model.embed_documents(texts)

    async def embed_query(self, text: str) -> Vector:
        with self.counting():
            return await self.model.embed_query(text)


class CountedSpeaker(Counted[SpeakerModel], SpeakerModel):
    @property
    def space(self) -> VoiceSpace:
        return self.model.space

    @property
    def threshold(self) -> float:
        return self.model.threshold

    async def embed(self, audio: bytes) -> Voiceprint:
        with self.counting():
            return await self.model.embed(audio)


class CountedTranscription(Counted[TranscriptionModel], TranscriptionModel):
    async def transcribe(self, audio: bytes, media_type: str) -> str:
        with self.counting():
            return await self.model.transcribe(audio, media_type)


class CountedSpeech(Counted[SpeechModel], SpeechModel):
    async def synthesize(self, text: str) -> bytes:
        with self.counting():
            return await self.model.synthesize(text)


class CountedImage(Counted[ImageModel], ImageModel):
    async def generate(self, prompt: str) -> Image:
        with self.counting():
            return await self.model.generate(prompt)


def metered(model: Model, consumer: Consumer, meter: Meter) -> Model:
    """`model`, counting each of its calls as `consumer`'s: a model of the same type."""
    match model:
        case LanguageModel():
            return CountedLanguage(model, consumer, meter)
        case EmbeddingModel():
            return CountedEmbedding(model, consumer, meter)
        case SpeakerModel():
            return CountedSpeaker(model, consumer, meter)
        case TranscriptionModel():
            return CountedTranscription(model, consumer, meter)
        case SpeechModel():
            return CountedSpeech(model, consumer, meter)
        case ImageModel():
            return CountedImage(model, consumer, meter)
    # a new type of model needs its counting wrapper
    raise ContractError(f"models.{consumer.key}: no meter for a {model.type} model")
