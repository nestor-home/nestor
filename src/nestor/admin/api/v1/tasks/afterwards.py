"""What the journal says happened to tasks: when each ended, the files it handed back, and where its result was
passed on."""

from dataclasses import dataclass
from datetime import datetime

from nestor.admin.state import AdminState
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation.events import TaskDelivered, TaskEnded
from nestor.modules.conversation import Source
from nestor.modules.initiative import Delivered
from nestor.modules.journal import BlobRef


@dataclass(frozen=True, slots=True)
class Delivery:
    at: datetime
    channel: str
    room: str | None  # when it was said aloud


@dataclass(frozen=True, slots=True)
class Afterwards:
    ended: dict[str, datetime]
    files: dict[str, tuple[BlobRef, ...]]  # what each task handed back, kept in the blob store
    delivered: dict[str, Delivery]  # in the conversation, or by the courier; the latest wins

    @classmethod
    async def of(cls, admin: AdminState) -> "Afterwards":
        nestor = admin.nestor
        spoken = nestor.spoken_channels()

        def delivery(at: datetime, address: Address) -> Delivery:
            return Delivery(at, address.channel, address.conversation if address.channel in spoken else None)

        delivered: dict[str, Delivery] = {}
        for event in await nestor.journal.history(TaskDelivered, Delivered):
            if isinstance(event, TaskDelivered):
                delivered[event.task_id] = delivery(event.at, event.address)
            elif event.about.source is Source.TASK:
                delivered[event.about.id] = delivery(event.at, event.address)
        ended = await nestor.journal.history(TaskEnded)
        return cls({e.task_id: e.at for e in ended}, {e.task_id: e.files for e in ended if e.files}, delivered)
