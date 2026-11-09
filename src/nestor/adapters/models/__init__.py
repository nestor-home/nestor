"""Models of `models`, one folder per provider and one file per type it serves (`elevenlabs/speech.py`).

Each file holds the model, a class deriving from its type's base (`LanguageModel`, `EmbeddingModel`,
`TranscriptionModel`, `SpeechModel`, `SpeakerModel`), its settings, `build` and the `plugin` that serves that type for
the provider. `common` is what the HTTP providers share, `pipecat` what the voice pipeline runs.
"""
