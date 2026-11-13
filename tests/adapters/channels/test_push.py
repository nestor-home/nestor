"""What the sending-only channels share, through one of them: a closed channel refuses to send."""

import pytest

from nestor.adapters.channels.webhook.channel import WebhookChannel
from nestor.core import ProviderError
from nestor.modules.channels import Address, Medium

from .push import Recorder


async def test_a_closed_channel_refuses_to_send() -> None:
    hook = WebhookChannel("webhook", url="https://hooks.test/nestor", transport=Recorder().transport)
    await hook.close()
    with pytest.raises(ProviderError):
        await hook.send(Address("webhook", "lea"), "?", Medium.WRITTEN, ())
