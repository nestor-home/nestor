"""Messages passed on: those not delivered yet and the questions waiting for an answer, each visible to whoever
it concerns (`journal.read.own`: the account's person sent or receives it; `journal.read.all`: every one)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import reaches_person_of
from nestor.admin.api.v1.messages.schemas import MessagesOut, PassedMessageOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["messages"])
Reader = Annotated[Caller, Depends(allowed(Scope.JOURNAL_READ_ALL, Scope.JOURNAL_READ_OWN))]


@router.get("/messages")
async def list_messages(request: Request, caller: Reader) -> MessagesOut:
    nestor = state(request).nestor
    book, people = nestor.message_book, People(nestor.household)

    def shown(messages: tuple) -> list[PassedMessageOut]:
        return [
            PassedMessageOut.of(m, people)
            for m in sorted(messages, key=lambda m: m.at, reverse=True)
            if reaches_person_of(caller, m.to, m.requested_by)
        ]

    return MessagesOut(pending=shown(book.pending()), questions=shown(book.open_questions()))
