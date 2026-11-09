"""Sensitive actions waiting for their person's go-ahead."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from nestor.admin.api.v1.shared import Input, OriginOut, People, PersonRef
from nestor.modules.initiative.confirmations import ConfirmationRequested


class ConfirmationOut(BaseModel):
    id: str
    person: PersonRef  # who must confirm, on their own account
    tool: str
    arguments: dict[str, Any]
    origin: OriginOut  # where it was asked (a room, aloud)
    expires_at: datetime
    yours: bool  # the caller is that person: they may answer here

    @classmethod
    def of(cls, request: ConfirmationRequested, people: People, caller_person: str | None) -> "ConfirmationOut":
        person = people.ref(request.person)
        assert person is not None
        return cls(
            id=request.confirmation_id,
            person=person,
            tool=request.tool,
            arguments=dict(request.arguments),
            origin=OriginOut(session=str(request.origin), channel=request.origin.channel),
            expires_at=request.expires_at,
            yours=request.person == caller_person,
        )


class AnswerIn(Input):
    approved: bool


class AnsweredOut(BaseModel):
    approved: bool
    result: str | None  # what the action answered, once run
