"""ImageModel over any OpenAI-compatible API, in either of its two forms:

- `images`: the `/images/generations` endpoint (OpenAI's gpt-image and DALL·E, Gemini's Imagen, local servers);
- `chat`: Chat Completions asked for an image (`modalities: [image, text]`), as OpenRouter serves its image models
  (Gemini's Flash Image, GPT-5 Image…).

The picture comes back as base64, a data URL, or an address it is fetched from. No vendor SDK."""

import base64
import binascii
from collections.abc import Mapping

from nestor.adapters.common.http import HttpApi, JsonApi
from nestor.adapters.models.common import brand
from nestor.adapters.models.openai_compatible.wire import ImageEndpoint, image
from nestor.modules.cognition.images import ImageModel
from nestor.modules.cognition.model import Image


class OpenAICompatibleImage(ImageModel):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        endpoint: ImageEndpoint = ImageEndpoint.IMAGES,
        size: str | None = None,
        extra_body: Mapping[str, object] | None = None,
        timeout_s: float = 120.0,
        provider: str = "openai-compatible-image",
    ) -> None:
        self._model, self._endpoint, self._size = model, endpoint, size
        self._extra_body = dict(extra_body or {})
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._api = JsonApi(provider, base_url.rstrip("/"), headers=headers, secret=api_key, timeout_s=timeout_s)
        self._files = HttpApi(provider, "", timeout_s=timeout_s)  # where a picture is given by address: no key
        self.brand = brand(base_url)

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def close(self) -> None:
        await self._api.aclose()
        await self._files.aclose()

    async def generate(self, prompt: str) -> Image:
        if self._endpoint is ImageEndpoint.CHAT:
            return await self._picture(await self._from_chat(prompt), "/chat/completions")
        return await self._picture(await self._from_images(prompt), "/images/generations")

    async def _from_images(self, prompt: str) -> object:
        """What `/images/generations` gives for `prompt`: base64 or an address."""
        body = {"model": self._model, "prompt": prompt, "n": 1} | ({"size": self._size} if self._size else {})
        answer = await self._api.post("/images/generations", body | self._extra_body)
        try:
            found = answer["data"][0]
            return found.get("b64_json") or found.get("url")
        except (KeyError, IndexError, TypeError, AttributeError):
            return None

    async def _from_chat(self, prompt: str) -> object:
        """What Chat Completions gives for `prompt`: the first picture of its answer (`message.images`, as OpenRouter
        returns them), a data URL."""
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
        }
        answer = await self._api.post("/chat/completions", body | self._extra_body)
        try:
            return answer["choices"][0]["message"]["images"][0]["image_url"]["url"]
        except (KeyError, IndexError, TypeError):
            return None

    async def _picture(self, given: object, path: str) -> Image:
        """A picture from what the provider gave: base64, a data URL, or an address to fetch it from."""
        if not isinstance(given, str) or not given:
            raise self._api.error(f"{path}: the answer holds no picture", transient=False)
        if given.startswith(("http://", "https://")):
            response = await self._files.request("GET", given)
            return image(response.content, response.headers.get("content-type"), self._api.error)
        media_type = None
        if given.startswith("data:"):
            header, _, given = given.partition(",")
            media_type = header.removeprefix("data:").split(";")[0] or None
        try:
            data = base64.b64decode(given, validate=True)
        except (binascii.Error, ValueError):
            raise self._api.error(f"{path}: the picture is not valid base64", transient=False) from None
        return image(data, media_type, self._api.error)
