"""The courier: delivers what the agent has to say unprompted, on the first channel that can take it."""

from collections.abc import Iterable, Mapping

from nestor.core import ProviderError
from nestor.modules.channels import Address, Channel
from nestor.modules.conversation import Agent, AssistantTurn
from nestor.modules.household import Person
from nestor.modules.initiative.events import Delivered, DeliveryFailed
from nestor.modules.journal import Journal


class Courier:
    def __init__(self, journal: Journal, agent: Agent, channels: Iterable[Channel]) -> None:
        self.journal, self.agent = journal, agent
        self.channels: Mapping[str, Channel] = {c.channel_id: c for c in channels}

    async def deliver(
        self, person: Person | None, instruction: str, *, candidates: Iterable[Address], about: str
    ) -> Address | None:
        """Try each address in order; the agent writes the message for the channel it goes to.

        Returns where it was delivered, or `None` (logged as `DeliveryFailed`) when no channel could take it.
        """
        tried: list[Address] = []
        for address in dict.fromkeys(candidates):  # in order, without duplicates
            channel = self.channels.get(address.channel)
            if channel is None or not channel.reachable(address):
                continue
            tried.append(address)
            text = await self.agent.compose(address, person, instruction)
            try:
                await channel.send(address, text)
            except ProviderError:
                continue
            await self.journal.publish(
                AssistantTurn(source="courier", session=address.session, address=address, text=text)
            )
            await self.journal.publish(
                Delivered(source="courier", address=address, about=about, person=person.id if person else None)
            )
            return address
        await self.journal.publish(
            DeliveryFailed(source="courier", about=about, tried=tuple(tried), person=person.id if person else None)
        )
        return None
