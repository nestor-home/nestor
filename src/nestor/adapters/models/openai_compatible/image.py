"""ImageModel over any OpenAI-compatible API, in either of its two forms:

- `images`: the `/images/generations` endpoint (OpenAI's gpt-image and DALL·E, Gemini's Imagen, local servers);
- `chat`: Chat Completions asked for an image (`modalities: [image, text]`), as OpenRouter serves its image models
  (Gemini's Flash Image, GPT-5 Image…).

The picture comes back as base64, a data URL, or an address it is fetched from. No vendor SDK."""

import base64
import binascii
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import Field, PositiveFloat

from nestor.adapters.common.http import JsonApi
from nestor.adapters.models.common import EndpointSettings, brand
from nestor.modules.channels import IMAGE_TYPES
from nestor.modules.cognition.images import ImageModel
from nestor.modules.cognition.model import Image
from nestor.runtime.plugins import Family, Plugin, Services

SIGNATURES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF8": "image/gif"}


class ImageEndpoint(StrEnum):
    IMAGES = "images"  # POST /images/generations
    CHAT = "chat"  # POST /chat/completions with `modalities`


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
        self.brand = brand(base_url)

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def close(self) -> None:
        await self._api.aclose()

    async def generate(self, prompt: str) -> Image:
        if self._endpoint is ImageEndpoint.CHAT:
            body: dict[str, Any] = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
            }
            answer = await self._api.post("/chat/completions", body | self._extra_body)
            return await self._picture(_chat_image(answer), "/chat/completions")
        body = {"model": self._model, "prompt": prompt, "n": 1} | ({"size": self._size} if self._size else {})
        answer = await self._api.post("/images/generations", body | self._extra_body)
        try:
            found = answer["data"][0]
        except (KeyError, IndexError, TypeError):
            raise self._api.error(f"/images/generations: no picture in {str(answer)[:200]}", transient=False) from None
        given = found.get("b64_json") or found.get("url")
        return await self._picture(given, "/images/generations")

    async def _picture(self, given: object, path: str) -> Image:
        """A picture from what the provider gave: base64, a data URL, or an address to fetch it from."""
        if not isinstance(given, str) or not given:
            raise self._api.error(f"{path}: the answer holds no picture", transient=False)
        if given.startswith(("http://", "https://")):
            response = await self._api.request("GET", given)
            return _image(response.content, response.headers.get("content-type"), self._api.error)
        media_type = None
        if given.startswith("data:"):
            header, _, given = given.partition(",")
            media_type = header.removeprefix("data:").split(";")[0] or None
        try:
            data = base64.b64decode(given, validate=True)
        except (binascii.Error, ValueError):
            raise self._api.error(f"{path}: the picture is not valid base64", transient=False) from None
        return _image(data, media_type, self._api.error)


def _chat_image(answer: Any) -> object:
    """The first picture of a Chat Completions answer (`message.images[].image_url.url`, as OpenRouter returns)."""
    try:
        return answer["choices"][0]["message"]["images"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError):
        return None


def _image(data: bytes, given: str | None, error: Any) -> Image:
    """`data` as a picture of a type people can see: its declared type, else the one its first bytes show."""
    media_type = (given or "").split(";")[0].strip().lower()
    if media_type not in IMAGE_TYPES:
        media_type = next((t for sig, t in SIGNATURES.items() if data.startswith(sig)), "")
        if not media_type and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            media_type = "image/webp"
    if media_type not in IMAGE_TYPES:
        raise error("the picture is of a type that cannot be shown", transient=False)
    return Image(media_type=media_type, data=data)


class OpenAICompatibleImageSettings(EndpointSettings):
    """An image model's profile."""

    model: str
    endpoint: ImageEndpoint = ImageEndpoint.IMAGES  # `chat` for OpenRouter's image models
    size: str | None = None  # `1024x1024`, `1536x1024`…, as the model takes it; its own default otherwise
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    timeout_s: PositiveFloat = Field(default=120.0, json_schema_extra={"advanced": True})


def build(settings: OpenAICompatibleImageSettings, name: str, services: Services) -> OpenAICompatibleImage:
    return OpenAICompatibleImage(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        endpoint=settings.endpoint,
        size=settings.size,
        extra_body=settings.extra_body,
        timeout_s=settings.timeout_s,
        provider=name,
    )


plugin = Plugin(Family.MODEL, "openai-compatible", OpenAICompatibleImageSettings, build, serves=ImageModel)
