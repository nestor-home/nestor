"""Messages passed on: those not delivered yet and the questions waiting for an answer, each visible to whoever
it concerns (`messages.read.own`: the account's person sent or receives it; `messages.read.all`: every one)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import reaches_message_of
from nestor.admin.api.v1.messages.schemas import MessagesOut, PassedMessageOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["messages"])
Reader = Annotated[Caller, Depends(allowed(Scope.MESSAGES_READ_ALL, Scope.MESSAGES_READ_OWN))]


@router.get("/messages")
async def list_messages(request: Request, caller: Reader) -> MessagesOut:
    """Each list oldest first, as the book keeps them."""
    nestor = state(request).nestor
    book, people = nestor.message_book, People(nestor.household)
    return MessagesOut(
        pending=[
            PassedMessageOut.of(m, people) for m in book.pending() if reaches_message_of(caller, m.to, m.requested_by)
        ],
        questions=[
            PassedMessageOut.of(m, people)
            for m in book.open_questions()
            if reaches_message_of(caller, m.to, m.requested_by)
        ],
    )
