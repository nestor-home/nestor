"""The courier: decides where an unprompted message goes, delivers it, and follows up in writing
when a spoken announcement gets no reaction (a closed door, the shower)."""

import asyncio
import contextlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from nestor.core import Component, PersonId, ProviderError, utc_now
from nestor.core.i18n import Message
from nestor.modules.channels import Address, AttachmentKind, Channel, Medium
from nestor.modules.conversation import About, Agent, Notification, Silence, UserTurn
from nestor.modules.home import PresenceSource
from nestor.modules.household import Person
from nestor.modules.initiative.delivery.events import Delivered, DeliveryConsidered, DeliveryFailed, DeliveryWithheld
from nestor.modules.initiative.delivery.policy import DeliveryPolicy, Plan
from nestor.modules.journal import FileRef, Journal

logger = logging.getLogger(__name__)

FOLLOW_UP = "You said this aloud a moment ago but nobody reacted; write it now, briefly, as a message."
NOTICE = (
    "This is said aloud in a room where others may hear, and its content is theirs: say only, in one short "
    "sentence, that something came for them and that you wrote it to them, nothing of what it says."
)
FILES_NOTICE = (
    "This is said aloud, and the files that come with it cannot be: say briefly what it brings, and that you wrote "
    "it to them with its files."
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
        conversation. A notification with nothing to tell is withheld there (`DeliveryWithheld`) and leaves no turn,
        unless it `must_tell`: then it goes on to the next place.
        `to` is a place asked for (a channel someone named): it is written there, whatever the policy.
        `private`: its content is the person's (a mail): aloud, others may hear, so the room only hears that something
        waits for them once the content is written; aloud in full only with nowhere to write. Files (a document a
        task made) cannot be said either: written with them, and the room hears what it brings."""
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
        unheard = plan.spoken is not None and bool(self._unsent(plan.spoken, notification.files))
        written_first = (private or unheard) and plan.spoken is not None and plan.written is not None
        # its content decides, written with its files; the room only hears of it once it is; when it cannot be
        # written after all, files are said aloud without what cannot be heard, private content never (tried again)
        if (
            written_first
            and plan.spoken
            and plan.written
            and (written_to := await self._send(person, plan.written, Medium.WRITTEN, notification))
        ):
            if written_to.said:
                said = NOTICE if private else FILES_NOTICE
                notice = replace(notification, text=f"{notification.text}\n\n{said}", files=())
                await self._send(person, plan.spoken, Medium.SPOKEN, notice)
            return written_to.address
        aloud = plan.spoken and not (private and written_first)
        if aloud and plan.spoken and (spoken := await self._send(person, plan.spoken, Medium.SPOKEN, notification)):
            if plan.follow_up and spoken.said:
                self._watch_reaction(person, plan, notification)
            return spoken.address
        if (
            plan.written
            and not written_first
            and (written_to := await self._send(person, plan.written, Medium.WRITTEN, notification))
        ):
            return written_to.address
        tried = tuple(a for a in (plan.spoken, plan.written) if a)
        await self.journal.publish(
            DeliveryFailed(
                source=self.name, about=notification.about, tried=tried, person=person.id if person else None
            )
        )
        return None

    def _unsent(self, address: Address, files: tuple[FileRef, ...]) -> tuple[FileRef, ...]:
        """The files the channel of `address` cannot send (a satellite sends none)."""
        channel = self.channels.get(address.channel)
        sends = channel.sends if channel else frozenset()
        return tuple(f for f in files if AttachmentKind.of(f.blob.media_type) not in sends)

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
        if unsent := self._unsent(address, notification.files):  # the model tells of the files that go only
            notification = replace(notification, files=tuple(f for f in notification.files if f not in unsent))
        conversations = self.agent.conversations
        who = person.id if person else None
        try:
            async with conversations.free(address):  # drafted after the answer being written, never in its middle
                draft = await self.agent.compose(address, person, notification, medium)
        except ProviderError as error:
            logger.warning("%s: the model could not write it for %s: %s", notification.about, address, error)
            return None
        if isinstance(draft, Silence):
            if notification.must_tell:
                logger.warning("%s: the model kept silent where it had to tell (%s)", notification.about, draft.reason)
                return None
            await self.journal.publish(
                DeliveryWithheld(
                    source=self.name, address=address, about=notification.about, person=who, reason=draft.reason
                )
            )
            return _Sent(address, said=False)
        attachments = self.agent.attachments
        files = await attachments.sent(draft.files, channel.sends)
        if draft.voiced:  # recorded once it is sure to go, as an answer to a voice message is
            files = await attachments.voice(draft.text) + files
        try:  # sent without holding the conversation: a voice says it once the person is answered
            await channel.send(address, draft.text, medium, files.sent)
        except ProviderError:
            return None
        async with conversations.free(address):  # recorded after what was said meanwhile, as it was heard
            await self.agent.delivered(address, person, notification, medium, draft.text, files.kept)
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
                    replace(notification, text=f"{notification.text}\n\n{FOLLOW_UP}"),
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
