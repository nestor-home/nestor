"""Discord's Gateway: the intents the bot asks for, the close codes reconnecting cannot get past, the heartbeat state of
one connection, and its frames, logged without the bot's token."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

# GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT
INTENTS = (1 << 9) | (1 << 12) | (1 << 15)
FATAL = {4004, 4010, 4011, 4012, 4013, 4014}  # bad token, sharding or intents refused: reconnecting will not help


class _RedactIdentify(logging.Filter):
    """websockets logs every frame at debug level, the Identify frame and its token included."""

    def filter(self, record: logging.LogRecord) -> bool:
        if '"token"' in record.getMessage():
            record.msg, record.args = "> TEXT <identify redacted>", None
        return True


frames = logging.getLogger(__name__)
frames.addFilter(_RedactIdentify())


@dataclass
class Beat:
    """What one gateway connection keeps: the last sequence number, whether the last heartbeat was acknowledged,
    whether Discord asked the bot to reconnect."""

    sequence: int | None = None
    acknowledged: bool = True
    asked_to_reconnect: bool = False


async def frames_of(socket: ClientConnection) -> AsyncIterator[str | bytes]:
    """The gateway's frames until it closes; `Fatal` when it closes with a code reconnecting cannot get past."""
    try:
        async for raw in socket:
            yield raw
    except ConnectionClosed as closed:
        if closed.rcvd is not None and closed.rcvd.code in FATAL:
            raise Fatal(closed.rcvd.code) from None
        raise


class Fatal(Exception):
    """The gateway closed with a code that reconnecting cannot get past."""
