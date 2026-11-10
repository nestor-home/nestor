"""The courier: decides where an unprompted message goes, delivers it, and follows up in writing
when a spoken announcement gets no reaction (a closed door, the shower)."""

import asyncio
import contextlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import Component, PersonId, ProviderError, utc_now
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Channel, Medium
from nestor.modules.conversation import SILENT, About, Agent, Notification, UserTurn
from nestor.modules.home import PresenceSource
from nestor.modules.household import Person
from nestor.modules.initiative.delivery.events import Delivered, DeliveryConsidered, DeliveryFailed, DeliveryWithheld
from nestor.modules.initiative.delivery.policy import DeliveryPolicy, Plan
from nestor.modules.journal import Journal

FOLLOW_UP = "You said this aloud a moment ago but nobody reacted; write it now, briefly, as a message."
NOTICE = (
    "This is said aloud in a room where others may hear, and its content is theirs: say only, in one short "
    "sentence, that something came for them and that you are writing it to them, nothing of what it says."
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FollowUp:
    """A message the courier will write at `due_at` unless someone answers what it said aloud."""

    about: About
    person: PersonId | None
    spoken: Address  # where it was said
    written: Address  # where it will be written
    due_at: datetime


@dataclass(frozen=True, slots=True)
class _Sent:
    """A conversation took a notification: `said` whether the agent had something to tell there, `False` when it
    withheld it."""

    address: Address
    said: bool


class Courier(Component):
    name = "courier"

    def __init__(
        self,
        journal: Journal,
        agent: Agent,
        channels: Iterable[Channel],
        *,
        policy: DeliveryPolicy | None = None,
        presence: PresenceSource | None = None,
        follow_up_after_s: float = 180.0,
    ) -> None:
        self.journal, self.agent = journal, agent
        self.channels: Mapping[str, Channel] = {c.channel_id: c for c in channels}
        self.policy = policy or DeliveryPolicy()
        self.presence = presence
        self.follow_up_after_s = follow_up_after_s
        self._follow_ups: dict[asyncio.Task[None], FollowUp] = {}

    def scheduled(self) -> tuple[FollowUp, ...]:
        """The written follow-ups still waiting, soonest first (they do not survive a restart)."""
        return tuple(sorted(self._follow_ups.values(), key=lambda f: f.due_at))

    async def close(self) -> None:
        for task in tuple(self._follow_ups):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def deliver(
        self,
        person: Person | None,
        notification: Notification,
        *,
        origin: Address | None = None,
        written: bool = False,
        urgent: bool = False,
        private: bool = False,
        to: Address | None = None,
    ) -> Address | None:
        """Deliver now what `notification` brings to `person`; returns where, or `None` (logged as `DeliveryFailed`)
        when nothing could take it. Wherever it goes, the notification and its answer become a turn of that
        conversation. A notification that may stay silent and has nothing to tell is withheld there
        (`DeliveryWithheld`) and leaves no turn; one that must be told and gets no answer goes on to the next place.
        `to` is a place asked for (a channel someone named): it is written there, whatever the policy.
        `private`: its content is the person's (a mail): aloud, others may hear, so the room only hears that something
        waits for them and the content is written at once; aloud in full only with nowhere to write."""
        plan = (
            Plan(spoken=None, written=to, reason=Message.of("delivery-place-asked", channel=to.channel))
            if to
            else self.policy.plan(
                person,
                channels=self.channels.values(),
                presence=self.presence.presence() if self.presence else None,
                origin=origin,
                now=utc_now(),
                written=written,
                urgent=urgent,
                origin_open=await self._open(origin),
            )
        )
        await self.journal.publish(
            DeliveryConsidered(
                source=self.name,
                about=notification.about,
                person=person.id if person else None,
                spoken=plan.spoken,
                written=plan.written,
                reason=plan.reason,
            )
        )
        if private and plan.spoken and plan.written:
            notice = Notification(f"{notification.text}\n\n{NOTICE}", notification.about)
            noticed = await self._send(person, plan.spoken, Medium.SPOKEN, notice)
            if noticed and (written_to := await self._send(person, plan.written, Medium.WRITTEN, notification)):
                return written_to.address
        elif plan.spoken and (spoken := await self._send(person, plan.spoken, Medium.SPOKEN, notification)):
            if plan.follow_up and spoken.said:
                self._watch_reaction(person, plan, notification)
            return spoken.address
        if plan.written and (written_to := await self._send(person, plan.written, Medium.WRITTEN, notification)):
            return written_to.address
        tried = tuple(a for a in (plan.spoken, plan.written) if a)
        await self.journal.publish(
            DeliveryFailed(
                source=self.name, about=notification.about, tried=tried, person=person.id if person else None
            )
        )
        return None

    async def _open(self, origin: Address | None) -> bool:
        """Whether the conversation it came from is spoken and still going on."""
        channel = self.channels.get(origin.channel) if origin else None
        if origin is None or channel is None or not channel.spoken:
            return False
        return await self.agent.conversations.current(origin, Medium.SPOKEN) is not None

    async def _send(
        self,
        person: Person | None,
        address: Address,
        medium: Medium,
        notification: Notification,
        *,
        follow_up: bool = False,
    ) -> _Sent | None:
        """Compose the answer to `notification` for this conversation once it is free, send it, then record both as
        its turn. `None`: this conversation could not take it, the model could not write it, or it wrote nothing
        for a notification that had to be told."""
        channel = self.channels.get(address.channel)
        if channel is None or not channel.reachable(address, medium):
            return None
        conversations = self.agent.conversations
        who = person.id if person else None
        try:
            async with conversations.free(address):  # drafted after the answer being written, never in its middle
                text = await self.agent.compose(address, person, notification, medium)
        except ProviderError:
            return None
        if text in ("", SILENT):
            if not notification.quiet:
                return None
            await self.journal.publish(
                DeliveryWithheld(source=self.name, address=address, about=notification.about, person=who)
            )
            return _Sent(address, said=False)
        try:  # sent without holding the conversation: a voice says it once the person is answered
            await channel.send(address, text, medium)
        except ProviderError:
            return None
        async with conversations.free(address):  # recorded after what was said meanwhile, as it was heard
            await self.agent.delivered(address, person, notification, medium, text)
        await self.journal.publish(
            Delivered(source=self.name, address=address, about=notification.about, person=who, follow_up=follow_up)
        )
        return _Sent(address, said=True)

    def _watch_reaction(self, person: Person | None, plan: Plan, notification: Notification) -> None:
        assert plan.spoken is not None and plan.written is not None
        spoken, written, since = plan.spoken, plan.written, utc_now()

        async def follow_up() -> None:
            await asyncio.sleep(self.follow_up_after_s)
            replies = await self.journal.history(UserTurn, session=spoken.session, since=since)
            if not replies:
                await self._send(
                    person,
                    written,
                    Medium.WRITTEN,
                    Notification(f"{notification.text}\n\n{FOLLOW_UP}", notification.about),
                    follow_up=True,
                )

        task = asyncio.create_task(follow_up(), name=f"follow-up {notification.about}")
        self._follow_ups[task] = FollowUp(
            about=notification.about,
            person=person.id if person else None,
            spoken=spoken,
            written=written,
            due_at=since + timedelta(seconds=self.follow_up_after_s),
        )
        task.add_done_callback(lambda done: self._follow_ups.pop(done, None))
