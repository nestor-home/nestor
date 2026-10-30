"""Journal entries as messages: what happened, to whom, through which channel, and why.

Each built-in event has its own message (`journal-*`, in `nestor/locales/*/journal.ftl`); any other
event gets `journal-<its type>` with its plain fields as arguments, so a plugin describes its events
by shipping that message. Raw content (what someone said, a tool's output) stays raw in `detail`.
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nestor.admin.presentation.phrasebook import Phrasebook
from nestor.core import ContractError, Event, PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import (
    AccountCreated,
    AccountDisabled,
    AccountEnabled,
    AccountInvited,
    AccountLocaleChanged,
    AccountLogin,
    AccountPasswordChanged,
    AccountRoleChanged,
    Accounts,
    InvitationRevoked,
)
from nestor.modules.channels import Address
from nestor.modules.cognition import (
    TaskAttached,
    TaskCancelRequested,
    TaskDelivered,
    TaskEnded,
    TaskProgressed,
    TaskStarted,
)
from nestor.modules.cognition.tools import ToolCalled, ToolCompleted
from nestor.modules.connectors import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.conversation import AnswerCut, AssistantTurn, FallbackSpoken, UserTurn
from nestor.modules.home import PresenceChanged
from nestor.modules.household import Household
from nestor.modules.initiative import (
    Delivered,
    DeliveryConsidered,
    DeliveryFailed,
    WatchCreated,
    WatchEnded,
    WatchTriggered,
)
from nestor.modules.journal import Entry
from nestor.modules.memory import MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.satellites import (
    PersonDetected,
    SatelliteConnected,
    SatelliteDisconnected,
    SatellitePaired,
    SatellitePairingRequested,
    SatelliteRevoked,
    SpeechActivityObserved,
)

DETAIL_LIMIT = 600
OTHER_KEY = "other"
_SUBJECT = re.compile(r"^(?:task (?P<task>\S+) (?P<status>\w+)|watch (?P<watch>\S+))(?P<follow> \(follow-up\))?$")


class Tone(StrEnum):
    NORMAL = "normal"
    DECISION = "decision"  # why the assistant spoke up
    WARNING = "warning"  # a failure worth a look


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    events: tuple[type[Event], ...]

    @property
    def types(self) -> frozenset[str]:
        return frozenset(e.event_type for e in self.events)


CATEGORIES = (
    Category("conversation", (UserTurn, AssistantTurn, FallbackSpoken, AnswerCut)),
    Category("delivery", (DeliveryConsidered, Delivered, DeliveryFailed)),
    Category("tool", (ToolCalled, ToolCompleted)),
    Category("task", (TaskStarted, TaskAttached, TaskProgressed, TaskCancelRequested, TaskEnded, TaskDelivered)),
    Category("watch", (WatchCreated, WatchTriggered, WatchEnded)),
    Category("memory", (MemoryRecorded, MemoryCorrected, MemoryForgotten)),
    Category("connection", (ConnectionCreated, ConnectionChanged, ConnectionRemoved)),
    Category("presence", (PresenceChanged,)),
    Category(
        "satellite",
        (SatellitePairingRequested, SatellitePaired, SatelliteRevoked, SatelliteConnected, SatelliteDisconnected),
    ),
    Category("observation", (PersonDetected, SpeechActivityObserved)),
    Category(
        "account",
        (
            AccountCreated,
            AccountRoleChanged,
            AccountDisabled,
            AccountEnabled,
            AccountPasswordChanged,
            AccountLocaleChanged,
            AccountInvited,
            InvitationRevoked,
            AccountLogin,
        ),
    ),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Line:
    at: datetime
    kind: str  # a category key, or `other`
    message: Message  # the summary
    detail: str = ""  # raw content: what was said, a tool's output (never translated)
    detail_message: Message | None = None  # a detail that is a sentence of ours
    reason: Message | None = None  # the decision's reason, shown prominently
    people: frozenset[PersonId] = field(default_factory=frozenset)
    channels: frozenset[str] = field(default_factory=frozenset)
    tone: Tone = Tone.NORMAL


def unknown_message(event_type: str, fields: Mapping[str, object] | None = None) -> Message:
    """`plugin.thing.happened` → `journal-plugin-thing-happened`, with the plain fields as arguments."""
    args = {k: v for k, v in (fields or {}).items() if isinstance(v, str | int | float) and not isinstance(v, bool)}
    return Message(f"journal-{re.sub(r'[._]', '-', event_type)}", {**args, "type": event_type})


def subject(about: str) -> dict[str, str]:
    """What an unprompted message was about, as arguments: `task 3f2a completed`, `watch 9d (follow-up)`."""
    match = _SUBJECT.match(about)
    if match is None:
        return {"subject": "other", "id": "", "status": "", "follow_up": "no", "about": about}
    kind = "task" if match["task"] else "watch"
    return {
        "subject": kind,
        "id": match["task"] or match["watch"],
        "status": match["status"] or "",
        "follow_up": "yes" if match["follow"] else "no",
        "about": about,
    }


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


class EventDescriber:
    """Describes entries for one reader: capability lists are named in the reader's language."""

    def __init__(
        self, household: Household, assistant: str, phrasebook: Phrasebook, accounts: Accounts | None = None
    ) -> None:
        self.household, self.assistant, self.phrasebook, self.accounts = household, assistant, phrasebook, accounts
        self._categories = {e: c for c in CATEGORIES for e in c.events}
        self._describers: Mapping[type[Event], Callable[..., Line]] = {
            UserTurn: self._user_turn,
            AssistantTurn: lambda e: self._line(
                e,
                Message.of("journal-assistant-answered", assistant=self.assistant, interrupted=_yes(e.interrupted)),
                detail=e.text,
                channels=[e.address],
            ),
            FallbackSpoken: lambda e: self._line(
                e, Message.of("journal-fallback", reason=e.reason), channels=[e.address], tone=Tone.WARNING
            ),
            AnswerCut: lambda e: self._line(
                e, Message.of("journal-answer-cut"), detail_message=Message.of("journal-detail-heard", heard=e.heard)
            ),
            ToolCalled: lambda e: self._line(
                e,
                Message.of("journal-tool-called", tool=e.name),
                detail=json.dumps(dict(e.arguments), ensure_ascii=False, default=str),
                people=[e.person],
                channels=[e.address],
            ),
            ToolCompleted: self._tool_completed,
            TaskStarted: lambda e: self._line(
                e,
                Message.of("journal-task-started", task=e.task_id, executor=e.executor),
                detail=e.objective,
                people=[e.requested_by],
                channels=[e.origin],
            ),
            TaskAttached: lambda e: self._line(e, Message.of("journal-task-attached", task=e.task_id)),
            TaskProgressed: lambda e: self._line(
                e, Message.of("journal-task-progressed", task=e.task_id), detail=e.step
            ),
            TaskCancelRequested: lambda e: self._line(e, Message.of("journal-task-cancel-requested", task=e.task_id)),
            TaskEnded: lambda e: self._line(
                e,
                Message.of("journal-task-ended", task=e.task_id, status=e.status, seconds=e.duration_s),
                detail=e.error or e.result or "",
                tone=Tone.WARNING if e.status == "failed" else Tone.NORMAL,
            ),
            TaskDelivered: lambda e: self._line(
                e, Message.of("journal-task-delivered", task=e.task_id), channels=[e.address]
            ),
            DeliveryConsidered: self._considered,
            Delivered: lambda e: self._line(
                e, Message("journal-delivered", subject(e.about)), people=[e.person], channels=[e.address]
            ),
            DeliveryFailed: lambda e: self._line(
                e,
                Message("journal-delivery-failed", subject(e.about)),
                detail_message=Message.of(
                    "journal-detail-tried", tried=", ".join(str(a) for a in e.tried), count=len(e.tried)
                ),
                people=[e.person],
                channels=e.tried,
                tone=Tone.WARNING,
            ),
            WatchCreated: lambda e: self._line(
                e,
                Message.of("journal-watch-created", what=e.what),
                detail_message=Message.of("journal-detail-keywords", keywords=", ".join(e.keywords))
                if e.keywords
                else None,
                people=[e.owner],
                channels=[e.created_in],
            ),
            WatchTriggered: lambda e: self._line(
                e,
                Message.of("journal-watch-triggered", watch=e.watch_id, item=e.item_title, urgent=_yes(e.urgent)),
                detail=e.summary,
            ),
            WatchEnded: lambda e: self._line(e, Message.of("journal-watch-ended", watch=e.watch_id, reason=e.reason)),
            MemoryRecorded: lambda e: self._line(
                e,
                Message.of("journal-memory-recorded"),
                detail=e.text,
                people=[e.about, e.told_by],
                channels=[e.learnt_in],
            ),
            MemoryCorrected: lambda e: self._line(
                e, Message.of("journal-memory-corrected"), detail=e.text, people=[e.by]
            ),
            MemoryForgotten: lambda e: self._line(e, Message.of("journal-memory-forgotten"), people=[e.by]),
            ConnectionCreated: lambda e: self._line(
                e, Message.of("journal-connection-created", account=e.account, kind=e.kind), people=[e.owner]
            ),
            ConnectionChanged: lambda e: self._line(
                e,
                Message.of("journal-connection-changed", connection=e.connection_id, status=e.status),
                detail=e.reason,
                tone=Tone.NORMAL if e.status == "connected" else Tone.WARNING,
            ),
            ConnectionRemoved: lambda e: self._line(
                e, Message.of("journal-connection-removed", connection=e.connection_id)
            ),
            PresenceChanged: self._presence,
            SatellitePairingRequested: lambda e: self._line(
                e,
                Message.of(
                    "journal-satellite-pairing-requested", device=e.device.id, model=e.device.model, room=e.device.room
                ),
                detail_message=self._capabilities("journal-detail-declares", e.capabilities),
            ),
            SatellitePaired: lambda e: self._line(
                e,
                Message.of("journal-satellite-paired", device=e.device.id, room=e.device.room),
                detail_message=self._capabilities("journal-detail-allowed", e.capabilities),
                people=[e.approved_by],
            ),
            SatelliteRevoked: lambda e: self._line(
                e,
                Message.of("journal-satellite-revoked", device=e.device_id),
                people=[e.revoked_by],
                tone=Tone.WARNING,
            ),
            SatelliteConnected: lambda e: self._line(
                e, Message.of("journal-satellite-connected", device=e.device_id, room=e.room)
            ),
            SatelliteDisconnected: lambda e: self._line(
                e, Message.of("journal-satellite-disconnected", device=e.device_id, room=e.room)
            ),
            PersonDetected: lambda e: self._line(
                e,
                Message.of("journal-person-detected", count=e.count, device=e.device_id, room=e.room),
                detail_message=Message.of("journal-detail-confidence", confidence=e.confidence),
            ),
            SpeechActivityObserved: lambda e: self._line(
                e,
                Message.of("journal-speech-activity", active=_yes(e.active), device=e.device_id, room=e.room),
            ),
            AccountCreated: lambda e: self._line(
                e, Message.of("journal-account-created", login=e.login, role=e.role.value), people=[e.person]
            ),
            AccountRoleChanged: lambda e: self._account(
                e, e.account_id, "journal-account-role-changed", role=e.role.value
            ),
            AccountDisabled: lambda e: self._account(e, e.account_id, "journal-account-disabled", tone=Tone.WARNING),
            AccountEnabled: lambda e: self._account(e, e.account_id, "journal-account-enabled"),
            AccountPasswordChanged: lambda e: self._account(e, e.account_id, "journal-account-password-changed"),
            AccountLocaleChanged: lambda e: self._account(
                e, e.account_id, "journal-account-locale-changed", locale=e.locale
            ),
            AccountInvited: lambda e: self._line(
                e,
                Message.of("journal-account-invited", role=e.role.value, **self._person(e.person)),
                people=[e.person],
            ),
            InvitationRevoked: lambda e: self._line(
                e, Message.of("journal-invitation-revoked", invitation=e.invitation_id)
            ),
            AccountLogin: self._login,
        }

    def describe(self, entry: Entry) -> Line:
        try:
            event = entry.event()
        except ContractError:  # written by a plugin no longer installed, or by a newer version
            payload = entry.record.get("payload")
            fields = payload if isinstance(payload, dict) else {}
            at = datetime.fromisoformat(str(entry.record["at"]))
            return Line(at=at, kind=OTHER_KEY, message=unknown_message(entry.type, fields))
        describer = self._describers.get(type(event))
        if describer:
            return describer(event)
        return self._line(event, unknown_message(event.event_type, event.to_record()["payload"]))  # ty: ignore[invalid-argument-type]

    def login(self, account_id: str | None) -> str:
        account = self.accounts.accounts.get(account_id or "") if self.accounts else None
        return account.login if account else str(account_id or "")

    def name(self, person: PersonId | None) -> str:
        if person is None:
            return ""
        try:
            return self.household.person(person).name
        except ContractError:
            return str(person)

    # -- the events that need more than one line --------------------------------------------------

    def _person(self, person: PersonId | None) -> dict[str, str]:
        return {"person": self.name(person), "known": _yes(person is not None)}

    def _user_turn(self, e: UserTurn) -> Line:
        return self._line(
            e,
            Message.of("journal-user-said", **self._person(e.person)),
            detail=e.text,
            people=[e.person],
            channels=[e.address],
        )

    def _tool_completed(self, e: ToolCompleted) -> Line:
        if e.ok:
            message = Message.of("journal-tool-completed", tool=e.name, seconds=e.duration_s)
            return self._line(e, message, detail=e.output)
        return self._line(e, Message.of("journal-tool-failed", tool=e.name), detail=e.output, tone=Tone.WARNING)

    def _considered(self, e: DeliveryConsidered) -> Line:
        way = {(True, True): "both", (True, False): "spoken", (False, True): "written"}.get(
            (e.spoken is not None, e.written is not None), "none"
        )
        plan = Message.of("journal-detail-plan", way=way, spoken=str(e.spoken or ""), written=str(e.written or ""))
        return self._line(
            e,
            Message("journal-delivery-considered", {**self._person(e.person), **subject(e.about)}),
            reason=e.reason,
            detail_message=plan,
            people=[e.person],
            channels=[e.spoken, e.written],
            tone=Tone.DECISION,
        )

    def _presence(self, e: PresenceChanged) -> Line:
        if e.home is False:
            where = "away"
        elif e.room:
            where = "room"
        elif e.home:
            where = "home"
        else:
            where = "unknown"
        message = Message.of("journal-presence-changed", person=self.name(e.person), where=where, room=e.room or "")
        return self._line(e, message, people=[e.person])

    def _capabilities(self, id: str, names: tuple[str, ...]) -> Message:
        labels = ", ".join(self.phrasebook.capability(n) for n in names)
        return Message.of(id, capabilities=labels, count=len(names))

    def _login(self, e: AccountLogin) -> Line:
        if e.succeeded:
            return self._account(e, e.account_id, "journal-login-succeeded")
        return self._account(
            e,
            e.account_id,
            "journal-login-failed",
            tone=Tone.WARNING,
            reason=e.reason,
            known=_yes(e.account_id is not None),
        )

    def _account(self, event: Event, account_id: str | None, id: str, *, tone: Tone = Tone.NORMAL, **args: str) -> Line:
        account = self.accounts.accounts.get(account_id or "") if self.accounts else None
        if account is not None and "role" not in args:
            args["role"] = account.role.value
        message = Message(id, {"login": self.login(account_id), **args})
        return self._line(event, message, people=[account.person if account else None], tone=tone)

    def _line(
        self,
        event: Event,
        message: Message,
        *,
        detail: str = "",
        detail_message: Message | None = None,
        reason: Message | None = None,
        people: Iterable[PersonId | None] = (),
        channels: Iterable[Address | None] = (),
        tone: Tone = Tone.NORMAL,
    ) -> Line:
        if len(detail) > DETAIL_LIMIT:
            detail = detail[:DETAIL_LIMIT] + "…"
        category = self._categories.get(type(event))
        return Line(
            at=event.at,
            kind=category.key if category else OTHER_KEY,
            message=message,
            detail=detail,
            detail_message=detail_message,
            reason=reason,
            people=frozenset(p for p in people if p),
            channels=frozenset(a.channel for a in channels if a),
            tone=tone,
        )
