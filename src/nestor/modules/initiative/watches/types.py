"""Watches and what they watch: items arriving from outside (a mail, a home event)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from nestor.core import PersonId, new_id, utc_now
from nestor.modules.channels import Address


@dataclass(frozen=True, slots=True, kw_only=True)
class Incoming:
    """Something that arrived from outside. Its text is data, never instructions."""

    source: str  # the connection it came through: "gmail-mathis"
    kind: str  # "mail", "home.event"…
    title: str
    body: str = ""
    sender: str | None = None
    owner: PersonId | None = None  # whose mailbox or account it came to
    data: Mapping[str, object] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True, kw_only=True)
class Watch:
    """A durable commitment: tell `owner` when something matching `what` arrives."""

    what: str  # in the person's words: "le colis Colissimo de la poussette"
    keywords: tuple[str, ...] = ()  # cheap first filter; empty means every item of the kinds
    kinds: tuple[str, ...] = ("mail",)
    owner: PersonId | None = None
    created_in: Address | None = None
    once: bool = True  # ends after the first match (a parcel arrives once)
    until: datetime | None = None
    id: str = field(default_factory=lambda: new_id()[:8])
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Verdict:
    """The triage model's answer about one item for one watch."""

    matches: bool
    urgent: bool = False
    summary: str = ""
