"""Doubles and the contract suite for image models: a model that draws what it is told, and the behaviour every
`ImageModel` adapter must show."""

from nestor.core import ProviderError
from nestor.modules.channels import IMAGE_TYPES
from nestor.modules.cognition.images import ImageModel
from nestor.modules.cognition.model import Image

PNG = b"\x89PNG\r\n\x1a\n"  # the start of every PNG file


class ScriptedImages(ImageModel):
    """Draws a PNG whose bytes end with the description, so a test can tell which picture is which."""

    name = "scripted-images"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> Image:
        self.prompts.append(prompt)
        if self.fail:
            raise ProviderError(self.name, "the picture was refused", transient=False)
        return Image(media_type="image/png", data=PNG + prompt.encode())


class ImageModelContract:
    """Behaviour every `ImageModel` adapter must show. Mix into a `Test…` class and implement `images()` and
    `unavailable_images()`."""

    def images(self) -> ImageModel:
        raise NotImplementedError

    def unavailable_images(self) -> ImageModel:
        raise NotImplementedError

    async def test_a_description_gives_one_picture_people_can_see(self) -> None:
        async with self.images() as images:
            picture = await images.generate("A black pebble with an orange bow tie")
        assert picture.media_type in IMAGE_TYPES
        assert picture.data

    async def test_a_provider_failure_is_a_provider_error(self) -> None:
        async with self.unavailable_images() as images:
            try:
                await images.generate("A black pebble with an orange bow tie")
            except ProviderError:
                return
        raise AssertionError("an unreachable provider must raise ProviderError")
