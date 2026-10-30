"""Conversations: the turns of one session that follow each other closely, counted as Home Assistant's
Assist counts them.

A conversation id is minted with the first turn and kept while turns keep coming: one that comes after
a longer silence than the channel allows opens a new conversation. Each channel decides
(`Channel.conversation_ends_after_s`): 5 minutes when spoken, as Assist; hours when written, as a
messaging thread. A session (`telegram:42`, `voice:salon`) is where people talk; a conversation is one
exchange there, never merged across channels, and it bounds what the agent replays to the model, as
Assist's chat log does. What must outlive it belongs in memories.

The open conversation of each session is rebuilt from the journal on first use, so a restart keeps
it while it lasts.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import SessionId, new_id, utc_now
from nestor.modules.channels import Address, Exchange
from nestor.modules.conversation.events import AssistantTurn, UserTurn
from nestor.modules.journal import Journal


@dataclass(frozen=True, slots=True)
class _Open:
    id: str
    last: datetime  # the latest turn


class Conversations:
    def __init__(
        self,
        journal: Journal,
        *,
        ends_after_s: Callable[[Address], float],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """`ends_after_s` gives the silence after which a turn at this address opens a new conversation."""
        self.journal = journal
        self._ends_after_s = ends_after_s
        self._clock = clock
        self._open: dict[SessionId, _Open] = {}
        self._loaded: set[SessionId] = set()

    async def turn(self, address: Address) -> Exchange:
        """A new turn in this session: in its open conversation, or in a new one when the last turn is
        too old. Nothing awaits between the decision and its record, so two turns starting together
        land in the same conversation."""
        session = address.session
        await self._load(session)
        now = self._clock()
        current = self._live(address, now)
        conversation = current.id if current else new_id()
        self._open[session] = _Open(conversation, now)
        return Exchange(conversation_id=conversation, turn_id=new_id())

    def ended(self, exchange: Exchange, address: Address) -> None:
        """The turn is over (its reply was written): the conversation's silence starts now."""
        current = self._open.get(address.session)
        if current is not None and current.id == exchange.conversation_id:
            self._open[address.session] = _Open(current.id, self._clock())

    async def current(self, address: Address) -> str | None:
        """The session's open conversation, without starting a turn; `None` when it has none."""
        await self._load(address.session)
        current = self._live(address, self._clock())
        return current.id if current else None

    def _live(self, address: Address, now: datetime) -> _Open | None:
        current = self._open.get(address.session)
        ends_after = timedelta(seconds=self._ends_after_s(address))
        return current if current is not None and now - current.last <= ends_after else None

    async def _load(self, session: SessionId) -> None:
        if session in self._loaded:
            return
        latest = await self.journal.history(UserTurn, AssistantTurn, session=session, newest_first=True, limit=1)
        self._loaded.add(session)
        if latest and (exchange := latest[0].exchange) is not None:
            self._open.setdefault(session, _Open(exchange.conversation_id, latest[0].at))
