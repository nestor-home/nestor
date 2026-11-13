"""The admin's chat as a channel: `kind: web`. The chat itself is the domain's (`ChatChannel`); the admin serves it."""

from nestor.adapters.channels.web.settings import WebSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "web", WebSettings, build)

__all__ = ["plugin"]
