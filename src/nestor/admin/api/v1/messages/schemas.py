"""Messages the agent passes on between people, and the questions still waiting for their answer."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.modules.initiative import MessageRequested


class PassedMessageOut(BaseModel):
    id: str
    to: PersonRef
    text: str
    requested_by: PersonRef | None  # None: the agent's own initiative
    expects_reply: bool
    channel: str | None  # a channel asked for
    at: datetime

    @classmethod
    def of(cls, message: MessageRequested, people: People) -> "PassedMessageOut":
        to = people.ref(message.to)
        assert to is not None
        return cls(
            id=message.message_id,
            to=to,
            text=message.text,
            requested_by=people.ref(message.requested_by),
            expects_reply=message.expects_reply,
            channel=message.channel,
            at=message.at,
        )


class MessagesOut(BaseModel):
    pending: list[PassedMessageOut]  # not delivered yet: waiting for a channel that takes them
    questions: list[PassedMessageOut]  # delivered, waiting for their answer
