"""Any OpenAI-compatible API (OpenRouter, OpenAI, Mistral, Groq, vLLM, Ollama, llama.cpp, Kokoro-FastAPI…), by type:

- `language`: its Chat Completions, streamed (`language.py`);
- `embedding`: its `/embeddings` endpoint (`embedding.py`);
- `image`: its `/images/generations` endpoint, or Chat Completions asked for an image (`image.py`);
- `transcription`: its `/audio/transcriptions` endpoint, for recordings and the satellites' voice (`transcription.py`);
- `speech`: its `/audio/speech` endpoint, for recordings and the satellites' voice (`speech.py`).

Each is configured by `base_url`, an optional `api_key` (local servers need none; the hosted providers known to
require one refuse to be configured without it) and its model (`settings.py`). No vendor SDK: httpx speaks the wire
protocol (`wire.py`, `stream.py`); the voice runs Pipecat's OpenAI services against the same endpoints (the
`voice` extra).
"""

from nestor.adapters.models.openai_compatible.settings import (
    OpenAICompatibleEmbeddingSettings,
    OpenAICompatibleImageSettings,
    OpenAICompatibleLanguageSettings,
    OpenAICompatibleSpeechSettings,
    OpenAICompatibleTranscriptionSettings,
    build_embedding,
    build_image,
    build_language,
    build_speech,
    build_transcription,
)
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.modules.cognition import LanguageModel
from nestor.modules.cognition.embedding import EmbeddingModel
from nestor.modules.cognition.images import ImageModel
from nestor.runtime.plugins import Family, Plugin

language = Plugin(
    Family.MODEL, "openai-compatible", OpenAICompatibleLanguageSettings, build_language, serves=LanguageModel
)
embedding = Plugin(
    Family.MODEL, "openai-compatible", OpenAICompatibleEmbeddingSettings, build_embedding, serves=EmbeddingModel
)
image = Plugin(Family.MODEL, "openai-compatible", OpenAICompatibleImageSettings, build_image, serves=ImageModel)
transcription = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleTranscriptionSettings,
    build_transcription,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
)
speech = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleSpeechSettings,
    build_speech,
    requires="nestor-home[voice]",
    serves=SpeechModel,
)

__all__ = ["embedding", "image", "language", "speech", "transcription"]
