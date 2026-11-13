"""Models of `models`, one package per provider (`elevenlabs/`), split by concern.

A provider's `__init__.py` documents it and holds one plugin per type it serves, named after the type
(`transcription`); `settings.py` holds each type's settings and `build_<type>`; one module per type holds its model, a
class deriving from the type's base (`LanguageModel`, `EmbeddingModel`, `ImageModel`, `TranscriptionModel`,
`SpeechModel`, `SpeakerModel`); the wire format it speaks has modules of its own. `common` is what the
OpenAI-compatible endpoints share, `pipecat` what the voice pipeline runs.
"""
