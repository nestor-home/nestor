"""What the journal says happened to tasks beyond their state: where what each turn came back with was passed on."""

from dataclasses import dataclass
from datetime import datetime

from nestor.admin.state import AdminState
from nestor.modules.cognition.delegation import TurnDelivered


@dataclass(frozen=True, slots=True)
class Delivery:
    at: datetime
    channel: str
    room: str | None  # when it was said aloud


@dataclass(frozen=True, slots=True)
class Afterwards:
    delivered: dict[str, Delivery]  # by turn: in the conversation, or by the courier; the latest wins

    @classmethod
    async def of(cls, admin: AdminState) -> "Afterwards":
        nestor = admin.nestor
        spoken = nestor.spoken_channels()
        return cls(
            {
                e.turn_id: Delivery(
                    e.at, e.address.channel, e.address.conversation if e.address.channel in spoken else None
                )
                for e in await nestor.journal.history(TurnDelivered)
            }
        )
