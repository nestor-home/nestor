"""Webhook channel: each message Nestor sends by itself is posted as JSON to an address: a Home Assistant
automation (which can notify its mobile app), n8n, a script of one's own.

A person's `reach` names a target (`webhook:<target>`), passed along so that one address serves several people. The
body is `{"to", "text", "attachments": [{"kind", "media_type", "name", "data"}]}`: `kind` is `image`, `voice`,
`audio` or `file` (a document), `name` the file's name when it has one, `data` in base64. With a `secret`, the body
is signed: `X-Nestor-Signature: sha256=<HMAC-SHA256 of the body>`, as GitHub signs its webhooks.
"""

from nestor.adapters.channels.webhook.settings import WebhookSettings, build
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(
    Family.CHANNEL,
    "webhook",
    WebhookSettings,
    build,
    card=Card(
        summary="Posts each message Nestor sends by itself as JSON to an address (Home Assistant, n8n, a script).",
        docs="channels#choose-channels",
        needs=(Need.SERVER,),
    ),
)

__all__ = ["plugin"]
