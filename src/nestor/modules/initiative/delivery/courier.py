"""The courier: decides where an unprompted message goes, delivers it, and follows up in writing
when a spoken announcement gets no reaction (a closed door, the shower)."""

import asyncio
import contextlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import Component, PersonId, ProviderError, utc_now
from nestor.modules.channels import Address, Channel
from nestor.modules.conversation import Agent, AssistantTurn, UserTurn
from nestor.modules.home import PresenceSource
from nestor.modules.household import Person
from nestor.modules.initiative.delivery.events import Delivered, DeliveryConsidered, DeliveryFailed
from nestor.modules.initiative.delivery.policy import DeliveryPolicy, Plan
from nestor.modules.journal import Journal

FOLLOW_UP = "You said this aloud a moment ago but nobody reacted; write it now, briefly, as a message."


@dataclass(frozen=True, slots=True, kw_only=True)
class FollowUp:
    """A message the courier will write at `due_at` unless someone answers what it said aloud."""

    about: str  # as journaled: `task 3f2a completed`, `watch w1`
    person: PersonId | None
    spoken: Address  # where it was said
    written: Address  # where it will be written
    due_at: datetime


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
        instruction: str,
        *,
        about: str,
        origin: Address | None = None,
        written: bool = False,
        urgent: bool = False,
    ) -> Address | None:
        """Deliver now; returns where, or `None` (logged as `DeliveryFailed`) when nothing could take it."""
        plan = self.policy.plan(
            person,
            channels=self.channels.values(),
            presence=self.presence.presence() if self.presence else None,
            origin=origin,
            now=utc_now(),
            written=written,
            urgent=urgent,
        )
        await self.journal.publish(
            DeliveryConsidered(
                source=self.name,
                about=about,
                person=person.id if person else None,
                spoken=plan.spoken,
                written=plan.written,
                reason=plan.reason,
            )
        )
        if plan.spoken and (spoken := await self._send(person, plan.spoken, instruction, about)):
            if plan.follow_up:
                self._watch_reaction(person, plan, instruction, about)
            return spoken
        if plan.written and (written_to := await self._send(person, plan.written, instruction, about)):
            return written_to
        tried = tuple(a for a in (plan.spoken, plan.written) if a)
        await self.journal.publish(
            DeliveryFailed(source=self.name, about=about, tried=tried, person=person.id if person else None)
        )
        return None

    async def _send(self, person: Person | None, address: Address, instruction: str, about: str) -> Address | None:
        channel = self.channels.get(address.channel)
        if channel is None or not channel.reachable(address):
            return None
        text = await self.agent.compose(address, person, instruction)
        try:
            await channel.send(address, text)
        except ProviderError:
            return None
        exchange = await self.agent.conversations.turn(address)  # an unprompted message is a turn of its own
        await self.journal.publish(
            AssistantTurn(source=self.name, session=address.session, address=address, text=text, exchange=exchange)
        )
        await self.journal.publish(
            Delivered(source=self.name, address=address, about=about, person=person.id if person else None)
        )
        return address

    def _watch_reaction(self, person: Person | None, plan: Plan, instruction: str, about: str) -> None:
        assert plan.spoken is not None and plan.written is not None
        spoken, written, since = plan.spoken, plan.written, utc_now()

        async def follow_up() -> None:
            await asyncio.sleep(self.follow_up_after_s)
            replies = await self.journal.history(UserTurn, session=spoken.session, since=since)
            if not replies:
                await self._send(person, written, f"{instruction}\n\n{FOLLOW_UP}", f"{about} (follow-up)")

        task = asyncio.create_task(follow_up(), name=f"follow-up {about}")
        self._follow_ups[task] = FollowUp(
            about=about,
            person=person.id if person else None,
            spoken=spoken,
            written=written,
            due_at=since + timedelta(seconds=self.follow_up_after_s),
        )
        task.add_done_callback(lambda done: self._follow_ups.pop(done, None))
