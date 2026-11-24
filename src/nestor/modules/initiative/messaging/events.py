"""Events of messages the agent passes on: asked for, then delivered or not. A message that expects a
reply opens a question; the message that `answers` it closes it."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange


class MessageRequested(Event, event_type="message.requested"):
    """Someone (`requested_by`, `None` for the agent's own initiative) has the agent tell `to` something.
    `in_writing` and `channel` constrain how; `answers` is the question it brings the answer to."""

    message_id: str
    to: PersonId
    text: str
    requested_by: PersonId | None = None
    origin: Address | None = None
    in_writing: bool = False
    channel: str | None = None
    expects_reply: bool = False
    answers: str | None = None
    exchange: Exchange | None = None


class MessageDelivered(Event, event_type="message.delivered"):
    message_id: str
    address: Address


class MessageUndelivered(Event, event_type="message.undelivered"):
    """No channel could take it; whoever asked is told."""

    message_id: str
