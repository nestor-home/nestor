"""The admin's chat as a channel: `kind: web`. The chat itself is the domain's (`ChatChannel`); the admin serves it."""

from nestor.adapters.channels.web.settings import WebSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(
    Family.CHANNEL,
    "web",
    WebSettings,
    build,
    card=Card(
        summary="People chat with Nestor in the admin, with files and voice messages.", docs="channels#choose-channels"
    ),
)

__all__ = ["plugin"]
