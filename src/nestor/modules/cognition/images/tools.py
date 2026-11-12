"""`generate_image`: the agent draws a picture and sends it with its answer, where the channel shows pictures."""

from collections.abc import Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.images.ports import ImageModel
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Made, Risk, Tool, ToolContext, ToolFailed, ToolProvider

GENERATE = ToolSpec(
    "generate_image",
    "Draw a picture from a description and send it with your answer, where the conversation shows pictures (a "
    "voice in a room does not). Describe what to show precisely: subject, setting, style, framing. Say you made it; "
    "do not describe it at length or give a link.",
    {
        "type": "object",
        "properties": {"description": {"type": "string", "description": "what the picture shows, in detail"}},
        "required": ["description"],
    },
)


class ImageTools(ToolProvider):
    name = "images"

    def __init__(self, model: ImageModel, *, timeout_s: float = 180.0) -> None:
        self._model, self._timeout_s = model, timeout_s

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=GENERATE, run=self.generate, risk=Risk.READ, timeout_s=self._timeout_s),)

    async def generate(self, arguments: Mapping[str, object], context: ToolContext) -> Made:
        description = str(arguments.get("description", "")).strip()
        if not description:
            raise ToolFailed("describe the picture to draw")
        try:
            image = await self._model.generate(description)
        except ProviderError as error:
            raise ToolFailed(f"the picture could not be drawn: {error}") from None
        picture = Attachment(kind=AttachmentKind.IMAGE, data=image.data, media_type=image.media_type)
        return Made({"made": "a picture, sent with your answer where the conversation shows pictures"}, (picture,))
