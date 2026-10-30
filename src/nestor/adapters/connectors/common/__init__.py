"""What mail connectors share: turning mail into readable text, pacing retries of an inbound feed."""

from nestor.adapters.connectors.common.retry import Backoff, Retry
from nestor.adapters.connectors.common.text import UNTRUSTED, cap, decode_header_value, html_to_text, tidy

__all__ = ["UNTRUSTED", "Backoff", "Retry", "cap", "decode_header_value", "html_to_text", "tidy"]
