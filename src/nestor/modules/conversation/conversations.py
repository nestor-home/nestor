"""Conversations: the turns of one session that follow each other closely, counted as Home Assistant's
Assist counts them.

A conversation id is minted with the first turn and kept while turns keep coming: one that comes after
a longer silence than its medium allows opens a new conversation: 5 minutes when spoken, as Assist;
hours when written, as a messaging thread (a channel may set its own, `conversation_ends_after_s`). A
device people both type on and talk to keeps one conversation: a typed follow-up to a spoken question
stays in it while the written silence allows. A session (`telegram:42`, `satellites:salon`) is where people
talk; a conversation is one exchange there, never merged across channels, and it bounds what the agent
replays to the model, as Assist's chat log does. What must outlive it belongs in memories.

The open conversation of each session is rebuilt from the journal on first use, so a restart keeps
it while it lasts.

This module is the only one that writes a conversation and reads it back, always in the journal: a `Turn` writes
what happens in one turn (what opened it, the answers, a cut, a fallback), `history` reads a conversation as the
model sees it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import Event, PersonId, SessionId, new_id, utc_now
from nestor.modules.channels import Address, Exchange, Medium
from nestor.modules.cognition.model import Message
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, FallbackSpoken, NotificationTurn, UserTurn
from nestor.modules.conversation.history import HISTORY_EVENTS, Names, in_conversation, to_messages
from nestor.modules.conversation.types import FallbackReason, Notification
from nestor.modules.identity import Speaker
from nestor.modules.journal import Journal

SOURCE = "agent"


class Turn:
    """One turn of a conversation, opened by a person's message or a notification: what is written in it goes
    through here, in the order it happened."""

    def __init__(self, conversations: "Conversations", address: Address, exchange: Exchange) -> None:
        self._conversations, self.address, self.exchange = conversations, address, exchange
        self._journal = conversations.journal

    async def said(self, text: str, medium: Medium, speaker: Speaker) -> UserTurn:
        """A person opened the turn."""
        return await self._publish(
            UserTurn(
                source=SOURCE,
                session=self.address.session,
                address=self.address,
                text=text,
                medium=medium,
                speaker=speaker,
                exchange=self.exchange,
            )
        )

    async def notified(self, notification: Notification, person: PersonId | None) -> NotificationTurn:
        """Nestor opened the turn with a notification for `person`."""
        return await self._publish(
            NotificationTurn(
                source=SOURCE,
                session=self.address.session,
                address=self.address,
                text=notification.text,
                about=notification.about,
                exchange=self.exchange,
                person=person,
            )
        )

    async def answered(self, text: str, *, interrupted: bool = False) -> AssistantTurn:
        return await self._publish(
            AssistantTurn(
                source=SOURCE,
                session=self.address.session,
                address=self.address,
                text=text,
                interrupted=interrupted,
                exchange=self.exchange,
            )
        )

    async def cut(self, answer: AssistantTurn, heard: str) -> AnswerCut:
        """The person cut in while `answer` was spoken: only `heard` reached them."""
        return await self._publish(
            AnswerCut(
                source=SOURCE, session=self.address.session, answer=answer.id, heard=heard, exchange=self.exchange
            )
        )

    async def fell_back(self, reason: FallbackReason) -> FallbackSpoken:
        return await self._publish(
            FallbackSpoken(
                source=SOURCE, session=self.address.session, address=self.address, reason=reason, exchange=self.exchange
            )
        )

    def end(self) -> None:
        """The turn is over (its answer was written or cut): the conversation's silence starts now."""
        self._conversations.ended(self.exchange, self.address)

    async def _publish[E: Event](self, event: E) -> E:
        await self._journal.publish(event)
        return event


@dataclass(frozen=True, slots=True)
class _Open:
    id: str
    last: datetime  # the latest turn


class Conversations:
    def __init__(
        self,
        journal: Journal,
        *,
        ends_after_s: Callable[[Address, Medium], float],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """`ends_after_s` gives the silence after which a turn at this address, through this medium,
        opens a new conversation."""
        self.journal = journal
        self._ends_after_s = ends_after_s
        self._clock = clock
        self._open: dict[SessionId, _Open] = {}
        self._loaded: set[SessionId] = set()

    async def turn(self, address: Address, medium: Medium) -> Turn:
        """A new turn in this session: in its open conversation, or in a new one when the last turn is
        too old. Nothing awaits between the decision and its record, so two turns starting together
        land in the same conversation."""
        session = address.session
        await self._load(session)
        now = self._clock()
        current = self._live(address, medium, now)
        conversation = current.id if current else new_id()
        self._open[session] = _Open(conversation, now)
        return Turn(self, address, Exchange(conversation_id=conversation, turn_id=new_id()))

    async def history(
        self, address: Address, conversation: str | None, *, max_events: int = 60, names: Names | None = None
    ) -> tuple[Message, ...]:
        """A conversation's last turns as the model reads them, whatever process held them (restarts included);
        nothing without one. Earlier conversations of the session are not replayed, as in Assist."""
        if conversation is None:
            return ()
        events = await self.journal.history(
            *HISTORY_EVENTS, session=address.session, newest_first=True, limit=max_events
        )
        return to_messages(in_conversation(reversed(events), conversation), names=names)

    async def fell_back(self, address: Address, reason: FallbackReason) -> FallbackSpoken:
        """A provider failed while drafting outside any turn (a notification's answer)."""
        event = FallbackSpoken(source=SOURCE, session=address.session, address=address, reason=reason)
        await self.journal.publish(event)
        return event

    def ended(self, exchange: Exchange, address: Address) -> None:
        """The turn is over (its reply was written): the conversation's silence starts now."""
        current = self._open.get(address.session)
        if current is not None and current.id == exchange.conversation_id:
            self._open[address.session] = _Open(current.id, self._clock())

    def over_after_s(self, address: Address) -> float:
        """The silence after which a conversation at this address is over whatever comes next: the longest
        its mediums allow (a spoken question may still get a typed follow-up)."""
        return max(self._ends_after_s(address, medium) for medium in Medium)

    async def current(self, address: Address, medium: Medium) -> str | None:
        """The session's open conversation for a turn through `medium`, without starting one; `None`
        when it has none."""
        await self._load(address.session)
        current = self._live(address, medium, self._clock())
        return current.id if current else None

    def _live(self, address: Address, medium: Medium, now: datetime) -> _Open | None:
        current = self._open.get(address.session)
        ends_after = timedelta(seconds=self._ends_after_s(address, medium))
        return current if current is not None and now - current.last <= ends_after else None

    async def _load(self, session: SessionId) -> None:
        if session in self._loaded:
            return
        latest = await self.journal.history(
            UserTurn, NotificationTurn, AssistantTurn, session=session, newest_first=True, limit=1
        )
        self._loaded.add(session)
        if latest and (exchange := latest[0].exchange) is not None:
            self._open.setdefault(session, _Open(exchange.conversation_id, latest[0].at))
