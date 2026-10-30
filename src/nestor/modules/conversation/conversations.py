"""Conversations: the turns of one session that follow each other closely, counted as Home Assistant's
Assist counts them.

A conversation id is minted with the first turn and kept while turns keep coming: one that comes more
than `ends_after_s` after the last one (5 minutes by default, as Assist) opens a new conversation. A
session (`telegram:42`, `voice:salon`) is where people talk; a conversation is one exchange there, and
it bounds what the agent replays to the model, as Assist's chat log does. What must outlive it belongs
in memories.

The open conversation of each session is rebuilt from the journal on first use, so a restart keeps
it while it lasts.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from nestor.core import ContractError, SessionId, new_id, utc_now
from nestor.modules.channels import Address, Exchange
from nestor.modules.conversation.events import AssistantTurn, UserTurn
from nestor.modules.journal import Journal

ENDS_AFTER_S = 300.0


@dataclass(frozen=True, slots=True)
class _Open:
    id: str
    last: datetime  # the latest turn


class Conversations:
    def __init__(
        self, journal: Journal, *, ends_after_s: float = ENDS_AFTER_S, clock: Callable[[], datetime] = utc_now
    ) -> None:
        if ends_after_s <= 0:
            raise ContractError("a conversation must last more than 0 s without a turn")
        self.journal = journal
        self.ends_after = timedelta(seconds=ends_after_s)
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
        current = self._live(session, now)
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
        current = self._live(address.session, self._clock())
        return current.id if current else None

    def _live(self, session: SessionId, now: datetime) -> _Open | None:
        current = self._open.get(session)
        return current if current is not None and now - current.last <= self.ends_after else None

    async def _load(self, session: SessionId) -> None:
        if session in self._loaded:
            return
        latest = await self.journal.history(UserTurn, AssistantTurn, session=session, newest_first=True, limit=1)
        self._loaded.add(session)
        if latest and (exchange := latest[0].exchange) is not None:
            self._open.setdefault(session, _Open(exchange.conversation_id, latest[0].at))
