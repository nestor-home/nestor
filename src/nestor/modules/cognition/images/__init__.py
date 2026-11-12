"""Pictures the agent draws: a model that turns a description into a picture, offered as `generate_image`."""

from nestor.modules.cognition.images.ports import ImageModel
from nestor.modules.cognition.images.tools import ImageTools

__all__ = ["ImageModel", "ImageTools"]
