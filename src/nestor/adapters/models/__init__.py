"""Model adapters: `openai_compatible` speaks any OpenAI-compatible Chat Completions API, `openai_embeddings` its
`/embeddings` endpoint."""

from nestor.adapters.models.openai_compatible import OpenAICompatibleModel, OpenAICompatibleSettings
from nestor.adapters.models.openai_embeddings import OpenAICompatibleEmbedder, OpenAICompatibleEmbedderSettings

__all__ = [
    "OpenAICompatibleEmbedder",
    "OpenAICompatibleEmbedderSettings",
    "OpenAICompatibleModel",
    "OpenAICompatibleSettings",
]
