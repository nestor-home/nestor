"""OpenAI-compatible image models: the contract over both forms of the API, mocked as each answers (base64, a data
URL, an address to fetch), and a picture of a type nobody could see refused."""

import base64
import json
from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.models.openai_compatible import OpenAICompatibleImage
from nestor.adapters.models.openai_compatible.image import ImageEndpoint
from nestor.core import ProviderError
from nestor.testing.cognition import ImageModelContract
from nestor.testing.cognition.images import PNG

BASE_URL = "https://images.test/v1"
KEY = "sk-images-0123456789"
JPEG = b"\xff\xd8\xff\xe0 a jpeg"


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post("https://down.test/v1/images/generations").respond(401, json={"error": {"message": f"bad {KEY}"}})
        router.post("https://down.test/v1/chat/completions").respond(401, json={"error": {"message": f"bad {KEY}"}})
        yield router


def model(endpoint: ImageEndpoint = ImageEndpoint.IMAGES, base_url: str = BASE_URL) -> OpenAICompatibleImage:
    return OpenAICompatibleImage(base_url=base_url, api_key=KEY, model="m", endpoint=endpoint, size="1024x1024")


class TestImagesEndpoint(ImageModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert (body["n"], body["size"]) == (1, "1024x1024")
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG + b"drawn").decode()}]})

        api.post(f"{BASE_URL}/images/generations").mock(side_effect=answer)

    def images(self) -> OpenAICompatibleImage:
        return model()

    def unavailable_images(self) -> OpenAICompatibleImage:
        return model(base_url="https://down.test/v1")


class TestChatEndpoint(ImageModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["modalities"] == ["image", "text"]
            url = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
            message = {"role": "assistant", "content": "", "images": [{"type": "image_url", "image_url": {"url": url}}]}
            return httpx.Response(200, json={"choices": [{"message": message}]})

        api.post(f"{BASE_URL}/chat/completions").mock(side_effect=answer)

    def images(self) -> OpenAICompatibleImage:
        return model(ImageEndpoint.CHAT)

    def unavailable_images(self) -> OpenAICompatibleImage:
        return model(ImageEndpoint.CHAT, base_url="https://down.test/v1")


async def test_a_picture_given_by_its_address_is_fetched_without_the_key(api: respx.MockRouter) -> None:
    api.post(f"{BASE_URL}/images/generations").respond(200, json={"data": [{"url": "https://cdn.test/p/1"}]})
    fetched = api.get("https://cdn.test/p/1").respond(200, content=JPEG, headers={"Content-Type": "image/jpeg"})
    async with model() as images:
        picture = await images.generate("un chat")
    assert (picture.media_type, picture.data) == ("image/jpeg", JPEG)
    assert "authorization" not in fetched.calls.last.request.headers, "the key is the provider's, not the host's"


@pytest.mark.parametrize(
    "answer",
    [{"data": []}, {"data": [{"b64_json": base64.b64encode(b"<svg/>").decode()}]}, {"data": [{"b64_json": "%%"}]}],
    ids=["no-picture", "a-type-nobody-can-see", "not-base64"],
)
async def test_an_answer_without_a_picture_to_show_is_a_provider_error(api: respx.MockRouter, answer: dict) -> None:
    api.post(f"{BASE_URL}/images/generations").respond(200, json=answer)
    async with model() as images:
        with pytest.raises(ProviderError) as failed:
            await images.generate("un chat")
    assert KEY not in str(failed.value)
