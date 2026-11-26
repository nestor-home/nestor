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
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime.plugins import Family, Plugin

language = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleLanguageSettings,
    build_language,
    serves=LanguageModel,
    card=Card(
        summary="Thinks and answers with any model behind an OpenAI-compatible API: OpenRouter, OpenAI, Mistral, "
        "Groq, Vercel (each with its key), or a local server (Ollama, llama.cpp, vLLM).",
        docs="models#choose-a-provider",
    ),
)
embedding = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleEmbeddingSettings,
    build_embedding,
    serves=EmbeddingModel,
    card=Card(
        summary="Searches memories by meaning with an embedding model behind an OpenAI-compatible API, hosted (with "
        "its key) or local.",
        docs="models#search-by-meaning",
    ),
)
image = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleImageSettings,
    build_image,
    serves=ImageModel,
    card=Card(
        summary="Draws and edits pictures with an image model behind an OpenAI-compatible API (OpenAI, OpenRouter).",
        docs="models#pictures",
        needs=(Need.KEY,),
    ),
)
transcription = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleTranscriptionSettings,
    build_transcription,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
    card=Card(
        summary="Hears speech with any OpenAI-compatible transcription API (OpenAI or Groq with a key, a local "
        "Whisper server).",
        docs="voice#choose-providers",
    ),
)
speech = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleSpeechSettings,
    build_speech,
    requires="nestor-home[voice]",
    serves=SpeechModel,
    card=Card(
        summary="Speaks with any OpenAI-compatible speech API (OpenAI with a key, a local Kokoro server).",
        docs="voice#choose-providers",
    ),
)

__all__ = ["embedding", "image", "language", "speech", "transcription"]
