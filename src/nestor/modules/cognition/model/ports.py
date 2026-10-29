"""The conversation model port: the fast central agent's language model.

The model receives the dialogue and the tools it may call, and streams back text and tool
calls. Streaming matters: the voice starts on the first sentence, not on the full answer.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from nestor.core import Component
from nestor.modules.cognition.model.types import ModelOutput, ModelRequest


class ConversationModel(Component, ABC):
    """Streams a reply to a request.

    Contract (checked by `nestor.testing.cognition.ConversationModelContract`):
    - the stream yields any number of `TextDelta` and `ToolCallRequested`, then exactly one `Finished`;
    - closing the stream early (`aclose`, on barge-in) stops generation and releases the request;
    - a provider failure raises `ProviderError`, never a vendor exception.
    """

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]: ...
