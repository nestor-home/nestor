"""Models that count their calls: each model of `models` is used through one of these, whatever its type, so that
every call reaches the ledger the same way. A wrapper changes nothing to what the caller sees: it is a model of the
same type, with the same capabilities, and leaves starting and closing the model to whoever owns it."""

from collections.abc import AsyncGenerator, Mapping, Sequence

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
from nestor.modules.usage.types import Attribution, Consumer, ConsumerKind


class Counted:
    """What every counting wrapper shares: it names, describes and reports the health of the model it wraps."""

    def __init__(self, model: Model, consumer: Consumer, meter: Meter) -> None:
        self.model, self.consumer, self.meter = model, consumer, meter
        self.name, self.brand, self.local = model.name, model.brand, model.local

    def health(self) -> Health:
        return self.model.health()

    def health_detail(self) -> Phrase | None:
        return self.model.health_detail()

    def notes(self) -> Sequence[str]:
        return self.model.notes()

    def details(self) -> Mapping[str, str]:
        return self.model.details()


class CountedLanguage(Counted, LanguageModel):
    def __init__(self, model: LanguageModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model
        self.vision, self.reads, self.document_pages = model.vision, model.reads, model.document_pages

    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        return self._stream(request, attribution())  # on behalf of whoever asks, whoever reads

    async def _stream(self, request: ModelRequest, said: Attribution) -> AsyncGenerator[ModelOutput]:
        with self.meter.measure(self.consumer, said) as call:
            async for output in counted(self._model.stream(request), call.tally):
                yield output


class CountedEmbedding(Counted, EmbeddingModel):
    def __init__(self, model: EmbeddingModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model

    @property
    def space(self) -> EmbeddingSpace:
        return self._model.space

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.embed_documents(texts)

    async def embed_query(self, text: str) -> Vector:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.embed_query(text)


class CountedSpeaker(Counted, SpeakerModel):
    def __init__(self, model: SpeakerModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model
        self.sample_rate = model.sample_rate

    @property
    def space(self) -> VoiceSpace:
        return self._model.space

    @property
    def threshold(self) -> float:
        return self._model.threshold

    async def embed(self, audio: bytes) -> Voiceprint:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.embed(audio)


class CountedTranscription(Counted, TranscriptionModel):
    def __init__(self, model: TranscriptionModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.transcribe(audio, media_type)


class CountedSpeech(Counted, SpeechModel):
    def __init__(self, model: SpeechModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model

    async def synthesize(self, text: str) -> bytes:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.synthesize(text)


class CountedImage(Counted, ImageModel):
    def __init__(self, model: ImageModel, consumer: Consumer, meter: Meter) -> None:
        super().__init__(model, consumer, meter)
        self._model = model

    async def generate(self, prompt: str) -> Image:
        with self.meter.measure(self.consumer) as call, counting(call.tally):
            return await self._model.generate(prompt)


def metered(key: str, model: Model, provider: str, asked: str | None, meter: Meter) -> Model:
    """`model` (`models.<key>`), counting each of its calls: a model of the same type. `provider`: its plugin's
    provider, named by the brand of its endpoint when known; `asked`: the model its settings name, to price it when
    the provider says nothing."""
    consumer = Consumer(
        key=key,
        kind=ConsumerKind(model.type.value),
        provider=model.brand or provider,
        model=asked,
        local=model.local,
    )
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
    raise ContractError(f"models.{key}: no meter for a {model.type} model")  # a new type needs its counting wrapper
