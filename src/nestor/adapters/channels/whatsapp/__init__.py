"""WhatsApp channel: a WhatsApp Business number through Meta's Cloud API, a `MessagingChannel`.

Meta posts each message to a webhook this channel serves on its own port (8473), behind a public HTTPS address the
household gives Meta (`https://<host>/whatsapp`, through its reverse proxy). The webhook is verified with
`verify_token`, and every post is checked against Meta's signature (`X-Hub-Signature-256`, the app secret). Text,
pictures, voice messages, audio files and documents reach the assistant; a voice message is answered with one (OGG/
Opus is what WhatsApp plays). Limits: WhatsApp lets a business answer freely only within 24 hours of the person's last
message, so a reminder sent later than that may be refused; a message received while Nestor was stopped is lost
once Meta gives up retrying.
"""

from nestor.adapters.channels.whatsapp.settings import WhatsAppSettings, build
from nestor.runtime.plugins import Family, Plugin

plugin = Plugin(Family.CHANNEL, "whatsapp", WhatsAppSettings, build)

__all__ = ["plugin"]
