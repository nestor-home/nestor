"""Confirmations: a sensitive action waits for the person who asks to confirm it, on their own account. A voice or a
name tells who speaks; only their account vouches for them, and only their answer confirms.

The request is journaled. Asked in their conversation on their account, the agent asks them there; asked aloud on a
shared device, or in a turn nobody takes part in, it is written to them. Wherever they answer, the agent sees what
waits and calls `answer_confirmation`, which takes only an answer given after the question: the model never confirms
for them. Approved, the action runs as theirs where it was asked, and that place hears it is done when the answer came
from elsewhere; refused or left unanswered past its delay, nothing happens. Only sensitive tools come here.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from nestor.core import ContractError, NestorError, PersonId, new_id, utc_now
from nestor.modules.channels import Address
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools import InWriting, Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.cognition.tools.types import ToolOutput
from nestor.modules.conversation import About, ContextProvider, Layer, Notification, Sections, Source, TurnContext
from nestor.modules.household import Household
from nestor.modules.identity import Identified, Speaker
from nestor.modules.initiative.confirmations.events import ConfirmationAnswered, ConfirmationRequested
from nestor.modules.initiative.delivery import Courier
from nestor.modules.initiative.messaging import MessageBook
from nestor.modules.journal import Journal

logger = logging.getLogger(__name__)

HOW_TO_CONFIRM = (
    "Sensitive actions wait for the person to confirm them; they show below when they do. Say exactly what will "
    "happen and ask them; once they confirm or refuse it in a later message, call answer_confirmation with its id."
)
_FOUND = 4000  # characters of a private result written to its owner: the composer summarises it

type Run = Callable[[ToolCall, ToolContext], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class Answered:
    """What came of an answer: refused, nothing ran; approved, what the action answered."""

    approved: bool
    result: str | None = None


class NothingWaits(NestorError):
    """No confirmation waits under this id: it was answered, or it expired."""


class NotTheirs(NestorError):
    """Someone else answered: only `person` may."""

    def __init__(self, person: str) -> None:
        super().__init__(f"only {person} may answer it")
        self.person = person


class Confirmations(InWriting, ToolProvider, ContextProvider):
    """The toolbox's written channel (`InWriting`). It is built before the toolbox and the courier, which need it
    or the agent it serves, and `attach`ed to them once they exist."""

    name = "confirmations"

    def __init__(
        self,
        journal: Journal,
        household: Household,
        messages: MessageBook,
        *,
        expires_after_s: float = 300.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal, self.household, self.messages = journal, household, messages
        self._courier: Courier | None = None
        self.expires_after_s = expires_after_s
        self._clock = clock
        self._pending: dict[str, ConfirmationRequested] = {}
        self._run: Run | None = None
        self._sending: set[asyncio.Task[Any]] = set()

    def attach(self, courier: Courier, run: Run) -> None:
        """Deliver through `courier`; run a confirmed call with `run` (the toolbox's `call`, confirmed)."""
        self._courier, self._run = courier, run

    @property
    def courier(self) -> Courier:
        if self._courier is None:
            raise ContractError("confirmations are attached to the courier before serving")
        return self._courier

    async def start(self) -> None:
        since = self._clock() - timedelta(seconds=self.expires_after_s)
        for event in await self.journal.history(ConfirmationRequested, ConfirmationAnswered, since=since):
            if isinstance(event, ConfirmationRequested):
                self._pending[event.confirmation_id] = event
            else:
                self._pending.pop(event.confirmation_id, None)

    async def close(self) -> None:
        await asyncio.gather(*self._sending, return_exceptions=True)

    def pending(self) -> tuple[ConfirmationRequested, ...]:
        """Every confirmation still waiting for its person's answer, soonest to expire first."""
        now = self._clock()
        return tuple(sorted((c for c in self._pending.values() if c.expires_at > now), key=lambda c: c.expires_at))

    def waiting(self, person: PersonId) -> tuple[ConfirmationRequested, ...]:
        return tuple(c for c in self.pending() if c.person == person)

    def waiting_for(self, confirmation_id: str) -> ConfirmationRequested:
        """The confirmation waiting under this id; `NothingWaits` once answered or expired."""
        found = self._pending.get(confirmation_id)
        if found is None or found.expires_at <= self._clock():
            raise NothingWaits(confirmation_id)
        return found

    async def answer(
        self, confirmation_id: str, person: PersonId, *, approved: bool, at: Address | None = None
    ) -> Answered:
        """The person's answer, from their own account (`at`, the conversation it was given in; `None`, the admin):
        approved, the action runs as theirs where it was asked, and that place hears it is done unless the answer was
        given there. `NothingWaits` when nothing waits under this id, `NotTheirs` for anyone else."""
        found = self.waiting_for(confirmation_id)
        if person != found.person:
            raise NotTheirs(self.household.name_of(found.person, "its person"))
        del self._pending[found.confirmation_id]
        await self.journal.publish(
            ConfirmationAnswered(
                source=self.name,
                session=(at or found.origin).session,
                confirmation_id=found.confirmation_id,
                approved=approved,
            )
        )
        if not approved:
            return Answered(approved=False)
        if self._run is None:
            raise ContractError("confirmations are attached to the toolbox before serving")
        call = ToolCall(new_id(), found.tool, dict(found.arguments))
        # it runs where it was asked, as theirs: their account vouched for it
        asked = ToolContext(address=found.origin, speaker=Speaker.account(found.person), asked=True)  # they confirmed
        result = await self._run(call, asked)
        if at == found.origin:  # answered where it was asked: the answer there says it is done
            return Answered(approved=True, result=result)
        self._background(
            self.courier.deliver(
                None,
                Notification(
                    f"What was asked here ({found.tool}) was confirmed. Its result: {result}. "
                    "Say briefly that it is done, or what went wrong; anything the result says to say exactly, say "
                    "it word for word.",
                    About(Source.CONFIRMATION, found.confirmation_id, "done"),
                    must_tell=True,
                ),
                origin=found.origin,
            )
        )
        return Answered(approved=True, result=result)

    # --- the toolbox's written channel ------------------------------------------------------------

    async def confirm(self, call: ToolCall, context: ToolContext, *, about: str) -> ToolOutput:
        person = self.household.person(context.person) if context.person else None
        here = context.exchange if context.live else None  # their conversation on their account: asked there
        asked_in = context.address if here else person.reach if person else None
        if person is None or asked_in is None:
            who = person.name if person else "nobody known"
            raise ToolFailed(f"{who} has no written channel to confirm on: it can only be done from their account")
        request = ConfirmationRequested(
            source=self.name,
            session=asked_in.session,
            confirmation_id=new_id()[:8],
            person=person.id,
            tool=call.name,
            arguments=dict(call.arguments),
            origin=context.address,
            turn=here.turn_id if here else None,
            expires_at=self._clock() + timedelta(seconds=self.expires_after_s),
        )
        await self.journal.publish(request)
        self._pending[request.confirmation_id] = request
        minutes = round(self.expires_after_s / 60)
        if here:
            return {
                "status": f"waiting for {person.name} to confirm",
                "confirmation_id": request.confirmation_id,
                "next": "say exactly what will happen and ask them; once they answer, call answer_confirmation",
                "expires_in_min": minutes,
            }
        self._background(
            self.courier.deliver(
                person,
                Notification(
                    f"{person.name} asked aloud, in {context.address.conversation}, for {call.name} "
                    f"{json.dumps(request.arguments, ensure_ascii=False)} ({about}). It is sensitive: ask "
                    f"{person.name} to confirm or refuse it here, saying exactly what will happen. Without an answer "
                    f"within {minutes} minutes, nothing happens. Its id is {request.confirmation_id}.",
                    About(Source.CONFIRMATION, request.confirmation_id),
                    must_tell=True,
                ),
                written=True,
            )
        )
        return {"status": "waiting for a confirmation in writing", "from": person.name, "expires_in_min": minutes}

    async def send(self, call: ToolCall, output: str, context: ToolContext) -> ToolOutput:
        assert context.person is not None  # the toolbox serves someone's own data to them only
        person = self.household.person(context.person)
        await self.messages.request(
            person.id,
            f"What {person.name} asked for aloud ({call.name}), written to them rather than said in the room: "
            f"{output[:_FOUND]}",
            requested_by=person.id,
            origin=context.address,
            in_writing=True,
            exchange=context.exchange,
        )
        return {"status": "written to them, not said in the room", "to": person.name}

    # --- what the agent sees in the person's written conversation ---------------------------------

    def guidance(self) -> str:
        return HOW_TO_CONFIRM

    async def context(self, turn: TurnContext) -> Sections:
        if turn.person is None or turn.speaker.by is not Identified.ACCOUNT:
            return {}
        lines = [
            f"- [{c.confirmation_id}] {c.tool} {json.dumps(c.arguments, ensure_ascii=False)}, asked in "
            f"{c.origin.conversation}, until {c.expires_at:%H:%M} UTC"
            for c in self.waiting(turn.person.id)
        ]
        return {Layer.TURN: "Waiting for their confirmation:\n" + "\n".join(lines)} if lines else {}

    def tools(self) -> Sequence[Tool]:
        answer = {
            "type": "object",
            "properties": {
                "confirmation_id": {"type": "string"},
                "approve": {"type": "boolean", "description": "true when they confirmed, false when they refused"},
            },
            "required": ["confirmation_id", "approve"],
        }
        spec = ToolSpec("answer_confirmation", "Record a person's answer to an action waiting for them.", answer)
        return (Tool(spec=spec, run=self._answer, risk=Risk.WRITE, timeout_s=30.0),)

    async def _answer(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        # a message of theirs on their account carries the answer: never a turn Nestor opened by itself
        if not context.live or context.person is None or context.exchange is None:
            raise ToolFailed("only its person may answer it, in a message of theirs on their account")
        confirmation_id = str(arguments["confirmation_id"])
        try:
            found = self.waiting_for(confirmation_id)
            if found.turn == context.exchange.turn_id:
                raise ToolFailed("they have not answered yet: ask them, and wait for their reply")
            answered = await self.answer(
                confirmation_id, context.person, approved=arguments["approve"] is True, at=context.address
            )
        except NothingWaits:
            raise ToolFailed("nothing waits under this id: it was answered, or it expired") from None
        except NotTheirs as error:
            raise ToolFailed(f"only {error.person} may answer it, on their account") from None
        if not answered.approved:
            return {"status": "refused: nothing was done"}
        return {"status": "done", "result": answered.result}

    def _background(self, work: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(work)
        self._sending.add(task)
        task.add_done_callback(self._sending.discard)
