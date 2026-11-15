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
      `reads`, nor one longer than its `document_pages`;
    - a tool call carries what its provider wants back with it within the turn (`replay`), if anything.
    """

    type = ModelType.LANGUAGE
    vision: bool = False  # whether it looks at the images of a message
    reads: frozenset[str] = frozenset()  # the media types of the documents it reads whole (a PDF), not as text
    document_pages: int | None = None  # the most pages of a document it reads whole; `None`: no limit

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]: ...


def reads_whole(reads: frozenset[str], limit: int | None, media_type: str, pages: int | None) -> bool:
    """Whether a model that `reads` these types, up to `limit` pages (`document_pages`), reads such a document whole;
    one whose pages were not counted is never sent to a model with a limit, which would refuse the whole request."""
    return media_type in reads and (limit is None or (pages is not None and pages <= limit))
