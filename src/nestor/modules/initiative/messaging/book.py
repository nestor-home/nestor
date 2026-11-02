"""The messages the agent was asked to pass on, rebuilt from the journal: which wait to be delivered,
which questions are still open."""

from nestor.core import Component, PersonId, new_id
from nestor.modules.channels import Address, Exchange
from nestor.modules.initiative.messaging.events import MessageDelivered, MessageRequested, MessageUndelivered
from nestor.modules.journal import Journal


class MessageBook(Component):
    """The only writer of messaging events: what it publishes is known at once, restarts included."""

    name = "message-book"

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self._messages: dict[str, MessageRequested] = {}
        self._settled: set[str] = set()  # delivered, or given up on
        self._answered: set[str] = set()

    async def start(self) -> None:
        for event in await self.journal.history(MessageRequested, MessageDelivered, MessageUndelivered):
            self._take(event)

    async def request(
        self,
        to: PersonId,
        text: str,
        *,
        requested_by: PersonId | None,
        origin: Address | None = None,
        in_writing: bool = False,
        channel: str | None = None,
        expects_reply: bool = False,
        answers: str | None = None,
        exchange: Exchange | None = None,
    ) -> MessageRequested:
        event = MessageRequested(
            source=self.name,
            session=origin.session if origin else None,
            message_id=new_id(),
            to=to,
            text=text,
            requested_by=requested_by,
            origin=origin,
            in_writing=in_writing,
            channel=channel,
            expects_reply=expects_reply,
            answers=answers,
            exchange=exchange,
        )
        await self._publish(event)
        return event

    async def delivered(self, message_id: str, address: Address) -> None:
        await self._publish(
            MessageDelivered(source=self.name, session=address.session, message_id=message_id, address=address)
        )

    async def undelivered(self, message_id: str) -> None:
        await self._publish(MessageUndelivered(source=self.name, message_id=message_id))

    def get(self, message_id: str) -> MessageRequested | None:
        return self._messages.get(message_id)

    def pending(self) -> tuple[MessageRequested, ...]:
        """Asked for but neither delivered nor given up on (a restart in between), oldest first."""
        return tuple(m for m in self._messages.values() if m.message_id not in self._settled)

    def open_questions(self) -> tuple[MessageRequested, ...]:
        """Questions passed on and not answered yet, oldest first."""
        return tuple(
            m
            for m in self._messages.values()
            if m.expects_reply and m.message_id in self._settled and m.message_id not in self._answered
        )

    async def _publish(self, event: MessageRequested | MessageDelivered | MessageUndelivered) -> None:
        await self.journal.publish(event)
        self._take(event)

    def _take(self, event: object) -> None:
        if isinstance(event, MessageRequested):
            self._messages[event.message_id] = event
            if event.answers:
                self._answered.add(event.answers)
        elif isinstance(event, MessageDelivered):
            self._settled.add(event.message_id)
        elif isinstance(event, MessageUndelivered):
            self._settled.add(event.message_id)
            self._answered.add(event.message_id)  # a question that never left cannot be answered
