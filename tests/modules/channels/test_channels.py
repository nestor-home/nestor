"""Addresses and sessions, and the in-memory channel the conversation service will be tested with."""

import asyncio

import pytest

from nestor.core import ContractError
from nestor.modules.channels import Address, InboundMessage
from nestor.testing.channels import InMemoryChannel, ScriptedAssistant, ScriptedReply


def test_an_address_round_trips_and_names_its_session() -> None:
    address = Address.parse("telegram:-1001234")

    assert address == Address("telegram", "-1001234")
    assert str(address) == "telegram:-1001234"
    assert address.session == Address("telegram", "-1001234").session != Address("voice", "-1001234").session
    with pytest.raises(ContractError, match="expected 'channel:conversation'"):
        Address.parse("telegram")


async def test_a_message_reaches_the_assistant_and_its_answer_comes_back() -> None:
    assistant = ScriptedAssistant(lambda m: f"Bonjour {m.sender.id} !")
    channel = InMemoryChannel("telegram")
    serving = asyncio.create_task(channel.serve(assistant))

    async with channel:
        answer = await channel.ask("Salut", sender="mathis", conversation="42")
    await asyncio.wait_for(serving, 1)  # closing the channel ends `serve`

    assert answer == "Bonjour mathis !"
    (message,) = assistant.messages
    assert message.address == Address("telegram", "42") and message.text == "Salut"


async def test_an_unprompted_message_is_only_delivered_on_its_own_channel() -> None:
    channel = InMemoryChannel("telegram")

    await channel.send(Address("telegram", "42"), "La tâche est finie.")
    with pytest.raises(ContractError, match="not on channel 'telegram'"):
        await channel.send(Address("voice", "salon"), "La tâche est finie.")

    assert channel.sent == [(Address("telegram", "42"), "La tâche est finie.")]


async def test_an_interrupted_reply_stops_and_keeps_what_was_heard() -> None:
    reply = ScriptedReply("Alors, les ours bruns et les grizzlys sont la même espèce.")
    spoken = []

    async for chunk in reply:
        spoken.append(chunk)
        if len(spoken) == 2:
            await reply.interrupt("".join(spoken))

    assert spoken == ["Alors,", " les"]
    assert reply.heard == "Alors, les"


async def test_an_assistant_failure_reaches_the_caller() -> None:
    def broken(message: InboundMessage) -> str:
        raise RuntimeError("model down")

    channel = InMemoryChannel()
    serving = asyncio.create_task(channel.serve(ScriptedAssistant(broken)))
    with pytest.raises(RuntimeError, match="model down"):
        await channel.ask("Salut")
    await channel.close()
    await asyncio.wait_for(serving, 1)
