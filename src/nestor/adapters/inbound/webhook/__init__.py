"""Webhooks as watch items: a service of one's own (GitHub, a Home Assistant automation, n8n, a script) posts JSON to
`POST /hooks/<name>` on Nestor's webhook port, and each post becomes an item of the kind its hook declares:
"tell me when a release of nestor is published", "when the washing machine is done".

Each hook has its secret. A post proves it holds it in either of two ways: a signature of its body,
`X-Hub-Signature-256: sha256=<HMAC-SHA256>` as GitHub signs (or `X-Nestor-Signature`, as Nestor's own webhook channel
signs), or `Authorization: Bearer <secret>` for a sender that cannot sign (Home Assistant's `rest_command`). A body is
read up to `max_bytes` and refused beyond. What a post brings is kept on disk before it is acknowledged (`202`), and
until it was yielded, so that a restart loses nothing accepted; a post sent while Nestor is down is refused by the
network, for its sender to retry. The port listens on the loopback by default: reach it from outside through a reverse
proxy that terminates TLS.
"""

from nestor.adapters.inbound.webhook.hooks import Hook
from nestor.adapters.inbound.webhook.settings import WebhookSettings, build
from nestor.adapters.inbound.webhook.source import WebhookSource
from nestor.runtime import Family, Plugin

__all__ = ["Hook", "WebhookSettings", "WebhookSource", "build", "plugin"]

plugin = Plugin(Family.INBOUND, "webhook", WebhookSettings, build)
