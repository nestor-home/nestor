"""Sensitive actions asked aloud, waiting for their person to confirm in writing. The person answers here as on
their account in a conversation: approved, the action runs as theirs and the room hears it is done."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import reaches_person_of
from nestor.admin.api.v1.confirmations.schemas import AnsweredOut, AnswerIn, ConfirmationOut
from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.modules.cognition.tools import ToolFailed

router = APIRouter(tags=["confirmations"])
Reader = Annotated[Caller, Depends(allowed(Scope.JOURNAL_READ_ALL, Scope.JOURNAL_READ_OWN))]


@router.get("/confirmations")
async def list_confirmations(request: Request, caller: Reader) -> list[ConfirmationOut]:
    """Those waiting, soonest to expire first."""
    nestor = state(request).nestor
    people = People(nestor.household)
    return [
        ConfirmationOut.of(c, people, caller.person)
        for c in nestor.confirmations.pending()
        if reaches_person_of(caller, c.person)
    ]


@router.post("/confirmations/{confirmation_id}/answer")
async def answer_confirmation(request: Request, caller: Reader, confirmation_id: str, body: AnswerIn) -> AnsweredOut:
    """Only the person asked may answer; 404 for anyone else, or once answered or expired."""
    confirmations = state(request).nestor.confirmations
    found = next((c for c in confirmations.pending() if c.confirmation_id == confirmation_id), None)
    if found is None or caller.person is None or found.person != caller.person:
        raise not_found("confirmation_unknown")
    try:
        answered = await confirmations.answer(
            found.confirmation_id, caller.person, approved=body.approved, session=found.origin.session
        )
    except ToolFailed:  # answered or expired meanwhile
        raise not_found("confirmation_unknown") from None
    result = answered.get("result")
    return AnsweredOut(approved=body.approved, result=str(result) if result is not None else None)
