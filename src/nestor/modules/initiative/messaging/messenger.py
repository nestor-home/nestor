"""Delivers the messages the agent was asked to pass on, once, even across restarts, and tells whoever
asked when one could not reach its person."""

import asyncio
import contextlib

from nestor.core import Component
from nestor.modules.household import Household, Person
from nestor.modules.initiative.delivery.courier import Courier
from nestor.modules.initiative.messaging.book import MessageBook
from nestor.modules.initiative.messaging.events import MessageRequested
from nestor.modules.journal import Subscription


class Messenger(Component):
    name = "messenger"

    def __init__(self, book: MessageBook, household: Household, courier: Courier) -> None:
        self.book, self.household, self.courier = book, household, courier
        self._subscription: Subscription | None = None
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self.book.journal.subscribe(MessageRequested)
        for message in self.book.pending():
            await self.deliver(message)
        self._worker = asyncio.create_task(self._listen(self._subscription), name="messenger")

    async def close(self) -> None:
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def deliver(self, message: MessageRequested) -> None:
        person = self.household.person(message.to)
        sender = self.household.person(message.requested_by) if message.requested_by else None
        address = await self.courier.deliver(
            person,
            self._instruction(message, person, sender),
            about=f"message {message.message_id}",
            # the conversation it was asked in is a way back only to whoever asked: never someone else's
            origin=message.origin if sender is not None and sender.id == person.id else None,
            written=message.in_writing,
            to=person.address_on(message.channel) if message.channel else None,
        )
        if address is not None:
            await self.book.delivered(message.message_id, address)
            return
        await self.book.undelivered(message.message_id)
        if sender is not None and sender.id != person.id:
            await self.courier.deliver(
                sender,
                f"You could not reach {person.name} to pass this on: {message.text}\n"
                f"Tell {sender.name} now, briefly, that the message did not get through.",
                about=f"message {message.message_id} undelivered",
                origin=message.origin,
            )

    def _instruction(self, message: MessageRequested, person: Person, sender: Person | None) -> str:
        question = self.book.get(message.answers) if message.answers else None
        if question is not None:
            asked = self.household.person(question.to).name
            lines = [f"{asked} answered the question you passed on for {person.name} ({question.text}): {message.text}"]
        elif sender is not None and sender.id != person.id:
            lines = [f"{sender.name} asked you to pass this on to {person.name}: {message.text}"]
        elif sender is None and message.origin is not None:  # someone at home nobody knows, on a shared device
            place = message.origin.conversation
            lines = [f"Someone at home, in {place}, asked you to pass this on to {person.name}: {message.text}"]
        else:
            lines = [f"What to tell {person.name}: {message.text}"]
        if message.expects_reply:
            whom = sender.name if sender else "you"
            lines.append(f"It is a question: ask it, and say their answer will reach {whom}.")
        lines.append(f"Say it to {person.name} now, unprompted and briefly, in your own words.")
        return "\n".join(lines)

    async def _listen(self, subscription: Subscription) -> None:
        async for event in subscription:
            if isinstance(event, MessageRequested):
                await self.deliver(event)
