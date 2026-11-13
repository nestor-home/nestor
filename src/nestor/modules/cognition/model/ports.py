"""The language model type: what writes the fast central agent's answers.

The model receives the dialogue and the tools it may call, and streams back text and tool
calls. Streaming matters: the voice starts on the first sentence, not on the full answer.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from nestor.core import Model, ModelType
from nestor.modules.cognition.model.types import ModelOutput, ModelRequest


class LanguageModel(Model, ABC):
    """Streams a reply to a request.

    Contract (checked by `nestor.testing.cognition.LanguageModelContract`):
    - the stream yields any number of `TextDelta` and `ToolCallRequested`, then exactly one `Finished`,
      which carries the usage and the model that answered when the provider reports them;
    - closing the stream early (`aclose`, on barge-in) stops generation and releases the request;
    - a provider failure raises `ProviderError`, never a vendor exception;
    - a model that does not see images (`vision` false) is never sent any, nor a document of a type it does not
      `reads`;
    - a tool call carries what its provider wants back with it within the turn (`replay`), if anything.
    """

    type = ModelType.LANGUAGE
    vision: bool = False  # whether it looks at the images of a message
    reads: frozenset[str] = frozenset()  # the media types of the documents it reads whole (a PDF), not as text

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]: ...
