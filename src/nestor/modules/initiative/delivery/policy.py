"""Where and how to deliver an unprompted message: a pure decision, explained in words.

- the person wants it in writing, or is away → message where they read;
- they are home → spoken by the satellite of the room they are in; when the home only knows that
  they are home, by the household's main satellite; then a message if nobody reacts;
- quiet hours → nothing spoken unless urgent; the message still goes (the phone decides how to ring);
- no presence information at all → the conversation it came from, else a message.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from nestor.core import ContractError
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Channel, Medium
from nestor.modules.home import Presence
from nestor.modules.household import Person


@dataclass(frozen=True, slots=True)
class QuietHours:
    start: time
    end: time

    @classmethod
    def parse(cls, text: str) -> "QuietHours":
        """`"22:30-07:30"`; a range may wrap past midnight."""
        try:
            start, end = (time.fromisoformat(part.strip()) for part in text.split("-"))
        except ValueError:
            raise ContractError(f"invalid quiet hours {text!r}, expected 'HH:MM-HH:MM'") from None
        return cls(start, end)

    def contains(self, moment: time) -> bool:
        if self.start <= self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    spoken: Address | None
    written: Address | None
    reason: Message  # why, rendered in the reader's language by a Localizer

    @property
    def follow_up(self) -> bool:
        """Spoken first, then written if nobody reacts."""
        return self.spoken is not None and self.written is not None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryPolicy:
    quiet_hours: QuietHours | None = None
    main_room: str | None = None  # where to speak when the home only knows that someone is home
    timezone: str = "Europe/Paris"

    def plan(
        self,
        person: Person | None,
        *,
        channels: Iterable[Channel],
        presence: Presence | None,
        origin: Address | None,
        now: datetime,
        written: bool = False,
        urgent: bool = False,
    ) -> Plan:
        channels = tuple(channels)
        spoken_ids = {c.channel_id for c in channels if c.medium is Medium.SPOKEN}
        satellites = {
            room: Address(c.channel_id, room) for c in channels if c.channel_id in spoken_ids for room in c.rooms
        }
        reach = person.reach if person else None
        fallback = reach or origin
        local = now.astimezone(ZoneInfo(self.timezone)).time()

        if written:
            return Plan(spoken=None, written=fallback, reason=Message.of("delivery-asked-in-writing"))
        if self.quiet_hours and self.quiet_hours.contains(local) and not urgent:
            return Plan(spoken=None, written=reach, reason=Message.of("delivery-quiet-hours"))
        if person is None or presence is None:
            back = origin if origin and origin.channel in spoken_ids else None
            return Plan(
                spoken=back,
                written=reach or (None if back else origin),
                reason=Message.of("delivery-no-presence"),
            )
        if presence.of(person.id).home is False:
            return Plan(spoken=None, written=fallback, reason=Message.of("delivery-away", person=person.name))
        rooms = presence.rooms_where(person.id)
        if rooms:
            here = sorted(r for r in rooms if r in satellites)
            if here:
                return Plan(
                    spoken=satellites[here[0]],
                    written=reach,
                    reason=Message.of("delivery-in-room", person=person.name, room=here[0]),
                )
            return Plan(
                spoken=None, written=fallback, reason=Message.of("delivery-room-without-satellite", person=person.name)
            )
        if presence.of(person.id).home and self.main_room in satellites:
            room = self.main_room
            return Plan(
                spoken=satellites[room],
                written=reach,
                reason=Message.of("delivery-home-main-satellite", person=person.name, room=room),
            )
        return Plan(spoken=None, written=fallback, reason=Message.of("delivery-no-satellite", person=person.name))
