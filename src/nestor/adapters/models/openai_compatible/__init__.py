"""Any OpenAI-compatible API (OpenRouter, OpenAI, vLLM, Ollama, llama.cpp…): its Chat Completions as a language
model, its `/embeddings` endpoint as an embedding model, its image generation as an image model. No vendor SDK:
httpx speaks the wire protocol."""

from nestor.adapters.models.openai_compatible.embedding import (
    OpenAICompatibleEmbedding,
    OpenAICompatibleEmbeddingSettings,
)
from nestor.adapters.models.openai_compatible.image import OpenAICompatibleImage, OpenAICompatibleImageSettings
from nestor.adapters.models.openai_compatible.language import OpenAICompatibleLanguage, OpenAICompatibleLanguageSettings

__all__ = [
    "OpenAICompatibleEmbedding",
    "OpenAICompatibleEmbeddingSettings",
    "OpenAICompatibleImage",
    "OpenAICompatibleImageSettings",
    "OpenAICompatibleLanguage",
    "OpenAICompatibleLanguageSettings",
]
