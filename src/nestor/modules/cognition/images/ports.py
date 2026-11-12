"""The image model port."""

from abc import ABC, abstractmethod

from nestor.core import Model, ModelType
from nestor.modules.cognition.model import Image


class ImageModel(Model, ABC):
    """Draws a picture from a description (text to image).

    Contract (checked by `nestor.testing.cognition.ImageModelContract`): `generate` returns one picture, of a type
    browsers and messaging apps show (`IMAGE_TYPES`); a provider failure, a refusal included, raises `ProviderError`,
    never a vendor exception."""

    type = ModelType.IMAGE

    @abstractmethod
    async def generate(self, prompt: str) -> Image: ...
