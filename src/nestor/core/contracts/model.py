"""What every model shares, whatever it serves: Nestor plugs models of a few types, each an abstract class.

A type is a base class the modules that use it own (`LanguageModel` in cognition, `SpeakerModel` in identity…), and
an adapter serves it for a provider by deriving from it. Configuration names a model by its type and provider, roles
and forms only offer the models of the type they need, and the runtime checks that what a plugin builds is one.
"""

from abc import ABC
from enum import StrEnum
from typing import ClassVar

from nestor.core.contracts.component import Component


class ModelType(StrEnum):
    LANGUAGE = "language"  # writes the answers
    EMBEDDING = "embedding"  # turns text into vectors, to search by meaning
    SPEAKER = "speaker"  # turns speech into voiceprints, to tell voices apart
    TRANSCRIPTION = "transcription"  # turns a person's speech into text (speech to text)
    SPEECH = "speech"  # gives the assistant its voice (text to speech)
    IMAGE = "image"  # draws a picture from a description


class Model(Component, ABC):
    """A model of `models`: a base class per `ModelType` derives from it and sets `type`."""

    def mirror(self, model: "Model") -> None:
        """Take on what `model` is (`MIRRORED`), to stand for it."""
        for attribute in self.MIRRORED:
            setattr(self, attribute, getattr(model, attribute))

    type: ClassVar[ModelType]
    # what a model that stands for another takes from it (a fallback chain, a counted model): a type adds its own
    # capabilities here, beside where it declares them, so that no wrapper forgets one
    MIRRORED: ClassVar[tuple[str, ...]] = ("name", "brand", "local")
    local: bool = False  # runs on hardware the household owns (sherpa-onnx, a server at home): nothing billed per call
