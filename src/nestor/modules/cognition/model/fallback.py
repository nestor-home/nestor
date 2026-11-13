"""A language model and the ones that answer when it cannot."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import replace

from nestor.core import ContractError, ProviderError
from nestor.modules.cognition.model.events import ModelFellBack
from nestor.modules.cognition.model.ports import LanguageModel
from nestor.modules.cognition.model.types import Message, ModelOutput, ModelRequest
from nestor.modules.journal import Journal

SOURCE = "models"


class FallingBack(LanguageModel):
    """The first of `chain` (key, model) answers; when one fails before its first output, the next is asked the same
    request, and the switch is journaled (`ModelFellBack`). A failure once the answer has started is the caller's: a
    second answer would repeat the first's beginning. It sees what the first sees: a fallback that does not see
    images, or does not read a document, gets the request without them. The models are started and closed by
    whoever owns them, not by it."""

    def __init__(self, chain: Sequence[tuple[str, LanguageModel]], journal: Journal) -> None:
        if len(chain) < 2:
            raise ContractError("a fallback chain needs a model and at least one fallback")
        self._chain, self._journal = tuple(chain), journal
        first = chain[0][1]
        self.name, self.brand, self.vision, self.reads = first.name, first.brand, first.vision, first.reads

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        for position, (key, model) in enumerate(self._chain):
            started = False
            try:
                asked = _for(model, request) if position else request  # the first sees all it was given
                async with aclosing(model.stream(asked)) as outputs:
                    async for output in outputs:
                        started = True
                        yield output
                return
            except ProviderError as error:
                if started or position == len(self._chain) - 1:
                    raise
                fallback = self._chain[position + 1][0]
                event = ModelFellBack(
                    source=SOURCE, model=key, fallback=fallback, error=str(error), transient=error.transient
                )
                await self._journal.publish(event)


def _for(model: LanguageModel, request: ModelRequest) -> ModelRequest:
    """`request` without what `model` cannot take: images it does not see, documents it does not read."""
    return replace(request, messages=tuple(_message_for(model, m) for m in request.messages))


def _message_for(model: LanguageModel, message: Message) -> Message:
    images = message.images if model.vision else ()
    documents = tuple(d for d in message.documents if d.media_type in model.reads)
    if images == message.images and documents == message.documents:
        return message
    return replace(message, images=images, documents=documents)
