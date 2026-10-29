"""Identifiers shared across the framework."""

from typing import NewType
from uuid import uuid4

SessionId = NewType("SessionId", str)
PersonId = NewType("PersonId", str)


def new_id() -> str:
    return uuid4().hex
