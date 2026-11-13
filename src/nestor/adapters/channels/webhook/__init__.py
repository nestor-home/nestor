"""Webhook channel: each message Nestor sends by itself is posted as JSON to an address: a Home Assistant
automation (which can notify its mobile app), n8n, a script of one's own.

A person's `reach` names a target (`webhook:<target>`), passed along so that one address serves several people. The
body is `{"to", "text", "attachments": [{"kind", "media_type", "name", "data"}]}`, `data` in base64. With a
`secret`, the body is signed: `X-Nestor-Signature: sha256=<HMAC-SHA256 of the body>`, as GitHub signs its webhooks.
"""

from nestor.adapters.channels.webhook.settings import WebhookSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "webhook", WebhookSettings, build)

__all__ = ["plugin"]
