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
    - a provider failure raises `ProviderError`, never a vendor exception.
    """

    type = ModelType.LANGUAGE

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]: ...
