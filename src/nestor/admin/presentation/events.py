"""Journal entries as messages: what happened, to whom, through which channel, and why.

Each built-in event has its own message (`journal-*`, in `nestor/locales/*/journal.ftl`); any other
event gets `journal-<its type>` with its plain fields as arguments, so a plugin describes its events
by shipping that message. Raw content (what someone said, a tool's output) stays raw in `detail`.
"""

import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
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
from nestor.modules.channels import Address, AttachmentKind
from nestor.modules.cognition import (
    TaskAttached,
    TaskCancelRequested,
    TaskDelivered,
    TaskEnded,
    TaskProgressed,
    TaskStarted,
)
from nestor.modules.cognition.tools import ResultStored, ToolCalled, ToolCompleted, ToolDeferred, ToolReturned
from nestor.modules.connectors import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.conversation import (
    About,
    AnswerAttached,
    AnswerCut,
    AssistantTurn,
    Attached,
    ConversationTitled,
    FallbackSpoken,
    NotificationTurn,
    SpeakerDeclared,
    UserTurn,
)
from nestor.modules.home import PresenceChanged
from nestor.modules.household import Household
from nestor.modules.identity import VoiceEnrolled, VoiceForgotten, VoiceLearningChanged
from nestor.modules.initiative import (
    Delivered,
    DeliveryConsidered,
    DeliveryFailed,
    DeliveryWithheld,
    MessageDelivered,
    MessageRequested,
    MessageUndelivered,
    ScheduleCancelled,
    ScheduleCreated,
    ScheduleFired,
    ToolResultDelivered,
    WatchCreated,
    WatchEnded,
    WatchSorted,
    WatchTriggered,
)
from nestor.modules.initiative.confirmations import ConfirmationAnswered, ConfirmationRequested
from nestor.modules.journal import Entry
from nestor.modules.memory import MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.episodes import EpisodeSummarized
from nestor.modules.satellites import (
    PersonDetected,
    SatelliteAdditionCancelled,
    SatelliteAdditionCompleted,
    SatelliteAdditionExpired,
    SatelliteAdditionStarted,
    SatelliteConnected,
    SatelliteDisconnected,
    SatelliteEnrollmentRefused,
    SatelliteIdentifyRequested,
    SatellitePaired,
    SatellitePairingRequested,
    SatelliteRevoked,
    SatelliteUpdateReported,
    SatelliteUpdateRequested,
    SpeechActivityObserved,
    UpdateState,
)
from nestor.modules.system import ConfigChanged, RestartRequested, SecretChanged, UpdateFailed, UpdateRequested

log = logging.getLogger(__name__)
DETAIL_LIMIT = 600
CLI = "cli"  # who did it, for an effect asked from the command line rather than by an account


class Tone(StrEnum):
    NORMAL = "normal"
    DECISION = "decision"  # why the assistant spoke up
    WARNING = "warning"  # a failure worth a look


class Kind(StrEnum):
    """What the journal groups entries by: the facets of its filters, one per category, and `other`."""

    CONVERSATION = "conversation"
    DELIVERY = "delivery"
    TOOL = "tool"
    TASK = "task"
    WATCH = "watch"
    SCHEDULE = "schedule"
    MEMORY = "memory"
    CONNECTION = "connection"
    PRESENCE = "presence"
    SATELLITE = "satellite"
    VOICE = "voice"
    OBSERVATION = "observation"
    ACCOUNT = "account"
    OTHER = "other"  # an event of no category: a plugin's, or a type this version does not know


CATEGORIES: Mapping[Kind, tuple[type[Event], ...]] = {
    Kind.CONVERSATION: (
        UserTurn,
        NotificationTurn,
        AssistantTurn,
        AnswerAttached,
        FallbackSpoken,
        AnswerCut,
        ConversationTitled,
    ),
    Kind.DELIVERY: (
        DeliveryConsidered,
        Delivered,
        DeliveryWithheld,
        DeliveryFailed,
        MessageRequested,
        MessageDelivered,
        MessageUndelivered,
    ),
    Kind.TOOL: (
        ToolCalled,
        ToolCompleted,
        ToolDeferred,
        ToolReturned,
        ResultStored,
        ToolResultDelivered,
        ConfirmationRequested,
        ConfirmationAnswered,
    ),
    Kind.TASK: (TaskStarted, TaskAttached, TaskProgressed, TaskCancelRequested, TaskEnded, TaskDelivered),
    Kind.WATCH: (WatchCreated, WatchSorted, WatchTriggered, WatchEnded),
    Kind.SCHEDULE: (ScheduleCreated, ScheduleFired, ScheduleCancelled),
    Kind.MEMORY: (MemoryRecorded, MemoryCorrected, MemoryForgotten, EpisodeSummarized),
    Kind.CONNECTION: (ConnectionCreated, ConnectionChanged, ConnectionRemoved),
    Kind.PRESENCE: (PresenceChanged,),
    Kind.SATELLITE: (
        SatellitePairingRequested,
        SatellitePaired,
        SatelliteRevoked,
        SatelliteConnected,
        SatelliteDisconnected,
        SatelliteUpdateRequested,
        SatelliteUpdateReported,
        SatelliteAdditionStarted,
        SatelliteAdditionCompleted,
        SatelliteAdditionCancelled,
        SatelliteAdditionExpired,
        SatelliteEnrollmentRefused,
        SatelliteIdentifyRequested,
    ),
    Kind.VOICE: (SpeakerDeclared, VoiceEnrolled, VoiceForgotten, VoiceLearningChanged),
    Kind.OBSERVATION: (PersonDetected, SpeechActivityObserved),
    Kind.ACCOUNT: (
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
}
if missing := set(Kind) - {Kind.OTHER} - set(CATEGORIES):
    raise ContractError(f"journal kinds without events: {sorted(missing)}")


@dataclass(frozen=True, slots=True, kw_only=True)
class Line:
    at: datetime
    kind: Kind
    message: Message  # the summary
    detail: str = ""  # raw content: what was said, a tool's output (never translated)
    detail_message: Message | None = None  # a detail that is a sentence of ours
    reason: Message | None = None  # the decision's reason, shown prominently
    people: frozenset[PersonId] = field(default_factory=frozenset)
    channels: frozenset[str] = field(default_factory=frozenset)
    tone: Tone = Tone.NORMAL
    room: str | None = None  # where it happened, when the event says
    tool: str | None = None  # the tool called
    outcome: tuple[bool, float] | None = None  # (succeeded, seconds) of a tool call or a task
    attachments: tuple[Attached, ...] = ()  # the files a person sent with their message


def unknown_message(event_type: str, fields: Mapping[str, object] | None = None) -> Message:
    """`plugin.thing.happened` → `journal-plugin-thing-happened`, with the plain fields as arguments."""
    args = {k: v for k, v in (fields or {}).items() if isinstance(v, str | int | float) and not isinstance(v, bool)}
    return Message(f"journal-{re.sub(r'[._]', '-', event_type)}", {**args, "type": event_type})


def subject(about: About, *, follow_up: bool = False) -> dict[str, str]:
    """What an unprompted message was about, as arguments of `journal-subject`: `task 3f2a completed`, `tool c1
    returned` (a call that went on in the background), `schedule s1`, `message 7c undelivered` (telling whoever
    asked that it did not get through)."""
    return {"subject": about.source.value, "id": about.id, "status": about.status, "follow_up": _yes(follow_up)}


def _room(event: Event) -> str | None:
    """The room an event names: its own `room`, or its device's (satellite events)."""
    room = getattr(event, "room", None)
    device = getattr(event, "device", None)
    return room if isinstance(room, str) else getattr(device, "room", None)


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


class EventDescriber:
    """Describes entries for one reader: capability lists are named in the reader's language."""

    def __init__(
        self, household: Household, assistant: str, phrasebook: Phrasebook, accounts: Accounts | None = None
    ) -> None:
        self.household, self.assistant, self.phrasebook, self.accounts = household, assistant, phrasebook, accounts
        self._categories = {e: kind for kind, events in CATEGORIES.items() for e in events}
        self._describers: Mapping[type[Event], Callable[..., Line]] = {
            UserTurn: self._user_turn,
            NotificationTurn: lambda e: self._line(
                e,
                Message("journal-notification-turn", {**subject(e.about), "assistant": self.assistant}),
                detail=e.text,
                people=[e.person],
                channels=[e.address],
            ),
            AssistantTurn: lambda e: self._line(
                e,
                Message.of(
                    "journal-assistant-interrupted" if e.interrupted else "journal-assistant-answered",
                    assistant=self.assistant,
                ),
                detail=e.text,
                channels=[e.address],
            ),
            FallbackSpoken: lambda e: self._line(
                e, Message.of("journal-fallback", reason=e.reason), channels=[e.address], tone=Tone.WARNING
            ),
            ConversationTitled: lambda e: self._line(e, Message.of("journal-conversation-titled", title=e.title)),
            AnswerAttached: lambda e: self._line(
                e,
                Message.of(
                    "journal-answer-voiced"
                    if any(f.kind is AttachmentKind.VOICE for f in e.files)
                    else "journal-answer-files",
                    assistant=self.assistant,
                    count=len(e.files),
                ),
                attachments=e.files,
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
                tool=e.name,
            ),
            ToolCompleted: self._tool_completed,
            ToolDeferred: lambda e: self._line(
                e,
                Message.of("journal-tool-deferred", tool=e.name),
                people=[e.person],
                channels=[e.address],
                tool=e.name,
            ),
            ToolReturned: self._tool_returned,
            ResultStored: lambda e: self._line(e, Message.of("journal-tool-result-stored", size=e.size)),
            ToolResultDelivered: lambda e: self._line(
                e, Message.of("journal-tool-result-delivered", tool=e.tool), channels=[e.address], tool=e.tool
            ),
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
                outcome=(e.status == "completed", e.duration_s),
            ),
            TaskDelivered: lambda e: self._line(
                e, Message.of("journal-task-delivered", task=e.task_id), channels=[e.address]
            ),
            DeliveryConsidered: self._considered,
            MessageRequested: lambda e: self._line(
                e,
                Message.of(
                    "journal-message-requested",
                    to=self.name(e.to),
                    kind="answer" if e.answers else "question" if e.expects_reply else "message",
                    by=self.name(e.requested_by) or self.assistant,
                ),
                detail=e.text,
                people=[e.requested_by, e.to],
                channels=[e.origin],
            ),
            ScheduleCreated: lambda e: self._line(
                e,
                Message.of("journal-schedule-created", recurring=_yes(e.once_at is None)),
                detail=e.instruction,
                people=[e.owner],
                channels=[e.created_in],
            ),
            ScheduleFired: lambda e: self._line(e, Message.of("journal-schedule-fired", id=e.schedule_id)),
            ScheduleCancelled: lambda e: self._line(
                e, Message.of("journal-schedule-cancelled", id=e.schedule_id), people=[e.by]
            ),
            MessageDelivered: lambda e: self._line(
                e, Message.of("journal-message-delivered", id=e.message_id), channels=[e.address]
            ),
            MessageUndelivered: lambda e: self._line(
                e, Message.of("journal-message-undelivered", id=e.message_id), tone=Tone.WARNING
            ),
            Delivered: lambda e: self._line(
                e,
                Message("journal-delivered", subject(e.about, follow_up=e.follow_up)),
                people=[e.person],
                channels=[e.address],
            ),
            DeliveryWithheld: lambda e: self._line(
                e, Message("journal-delivery-withheld", subject(e.about)), people=[e.person], channels=[e.address]
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
                people=[e.owner],
                channels=[e.created_in],
            ),
            WatchSorted: lambda e: self._line(
                e,
                Message.of(
                    "journal-watch-sorted",
                    item=e.item_title,
                    matched=len(e.matched),
                    asked=len(e.asked),
                    unsorted=_yes(e.unsorted),
                ),
                tone=Tone.WARNING if e.unsorted else Tone.NORMAL,
            ),
            WatchTriggered: lambda e: self._line(
                e,
                Message.of("journal-watch-triggered", watch=e.watch_id, item=e.item_title, urgent=_yes(e.urgent)),
                detail=e.summary,
            ),
            WatchEnded: lambda e: self._line(e, Message.of("journal-watch-ended", watch=e.watch_id, reason=e.reason)),
            MemoryRecorded: lambda e: self._line(
                e,
                Message.of("journal-memory-recorded", drawn=_yes(e.episode is not None)),
                detail=e.text,
                people=[e.about, e.told_by],
                channels=[e.learnt_in],
            ),
            MemoryCorrected: lambda e: self._line(
                e, Message.of("journal-memory-corrected"), detail=e.text, people=[e.by]
            ),
            MemoryForgotten: lambda e: self._line(e, Message.of("journal-memory-forgotten"), people=[e.by]),
            EpisodeSummarized: lambda e: self._line(
                e,
                Message.of("journal-episode-summarized", kept=_yes(bool(e.summary))),
                detail=e.summary,
                people=e.participants,
                channels=[e.address],
            ),
            ConnectionCreated: lambda e: self._line(
                e, Message.of("journal-connection-created", account=e.account, kind=e.kind), people=[e.owner]
            ),
            ConnectionChanged: lambda e: self._line(
                e,
                Message.of("journal-connection-changed", connection=e.connection_id, status=e.status),
                detail_message=e.reason,
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
                Message.of("journal-satellite-paired", device=e.device.id, room=e.device.room, proof=e.proof.value),
                detail_message=self._capabilities("journal-detail-allowed", e.capabilities),
                people=[e.approved_by],
            ),
            SatelliteAdditionStarted: lambda e: self._line(
                e,
                Message.of("journal-satellite-addition-started", proof=e.method.proof.value),
                people=[e.created_by],
                room=e.room,
            ),
            SatelliteAdditionCompleted: lambda e: self._line(
                e, Message.of("journal-satellite-addition-completed", device=e.device_id)
            ),
            SatelliteAdditionCancelled: lambda e: self._line(
                e, Message.of("journal-satellite-addition-cancelled"), people=[e.cancelled_by]
            ),
            SatelliteAdditionExpired: lambda e: self._line(e, Message.of("journal-satellite-addition-expired")),
            SatelliteEnrollmentRefused: lambda e: self._line(
                e,
                Message.of("journal-satellite-enrollment-refused", device=e.device_id, reason=e.reason),
                tone=Tone.WARNING,
            ),
            SatelliteIdentifyRequested: lambda e: self._line(
                e, Message.of("journal-satellite-identify-requested", device=e.device_id), people=[e.requested_by]
            ),
            SatelliteRevoked: lambda e: self._line(
                e,
                Message.of("journal-satellite-revoked", device=e.device_id),
                people=[e.revoked_by],
                tone=Tone.WARNING,
            ),
            SatelliteConnected: lambda e: self._line(
                e,
                Message.of("journal-satellite-connected", device=e.device_id, room=e.room),
                detail_message=Message.of("journal-detail-software", name=e.software.name, version=e.software.version),
            ),
            SatelliteUpdateRequested: lambda e: self._line(
                e,
                Message.of(
                    "journal-satellite-update-requested", device=e.device_id, running=e.running, target=e.target
                ),
                people=[e.requested_by],
            ),
            SatelliteUpdateReported: lambda e: self._line(
                e,
                Message.of(
                    "journal-satellite-update-reported", device=e.device_id, state=e.state.value, target=e.target or ""
                ),
                tone=Tone.WARNING if e.state is UpdateState.FAILED else Tone.NORMAL,
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
                e,
                e.account_id,
                "journal-account-locale-changed",
                locale=e.locale or "",
                chosen=_yes(e.locale is not None),  # no: back to the household's language
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
            SpeakerDeclared: lambda e: self._line(
                e,
                Message.of("journal-speaker-declared", person=self.name(e.person)),
                people=[e.person],
                channels=[e.address],
            ),
            VoiceEnrolled: lambda e: self._line(
                e,
                Message.of("journal-voice-enrolled", person=self.name(e.person), where=e.where),
                people=[e.person],
            ),
            VoiceForgotten: lambda e: self._line(
                e,
                Message.of("journal-voice-forgotten", person=self.name(e.person), learned=_yes(e.learned_only)),
                people=[e.person],
            ),
            VoiceLearningChanged: lambda e: self._line(
                e,
                Message.of("journal-voice-learning", person=self.name(e.person), learning=_yes(e.learning)),
                people=[e.person],
            ),
            ConfirmationRequested: lambda e: self._line(
                e,
                Message.of("journal-confirmation-requested", person=self.name(e.person), tool=e.tool),
                people=[e.person],
                channels=[e.origin],
                tool=e.tool,
            ),
            ConfirmationAnswered: lambda e: self._line(
                e, Message.of("journal-confirmation-answered", approved=_yes(e.approved))
            ),
            ConfigChanged: self._config_changed,
            SecretChanged: lambda e: self._by(e, e.by, "journal-secret-changed", name=e.name, removed=_yes(e.removed)),
            RestartRequested: lambda e: self._by(e, e.by, "journal-system-restart-requested", tone=Tone.WARNING),
            UpdateRequested: lambda e: self._by(
                e, e.by, "journal-system-update-requested", running=e.running, target=e.target
            ),
            UpdateFailed: lambda e: self._line(
                e, Message.of("journal-system-update-failed", target=e.target), tone=Tone.WARNING
            ),
        }

    def describe(self, entry: Entry) -> Line:
        """Never raises: a stored event is always shown, at worst by its type (a bug in describing one
        entry must not hide the rest of the journal)."""
        at = datetime.fromisoformat(str(entry.record["at"]))
        try:
            event = entry.event()
        except ContractError:  # written by a plugin no longer installed, or by a newer version
            payload = entry.record.get("payload")
            fields = payload if isinstance(payload, dict) else {}
            return Line(at=at, kind=Kind.OTHER, message=unknown_message(entry.type, fields))
        try:
            describer = self._describers.get(type(event))
            if describer:
                return describer(event)
            return self._line(event, unknown_message(event.event_type, event.to_record()["payload"]))  # ty: ignore[invalid-argument-type]
        except Exception:
            log.exception("cannot describe journal entry %s (%s)", entry.position, entry.type)
            return Line(
                at=at,
                kind=self._categories.get(type(event), Kind.OTHER),
                message=Message.of("journal-other", type=entry.type),
                tone=Tone.WARNING,
            )

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
            Message.of("journal-user-said", by=e.speaker.by.value, **self._person(e.person)),
            detail=e.text,
            people=[e.person],
            channels=[e.address],
            attachments=e.attachments,
        )

    def _tool_returned(self, e: ToolReturned) -> Line:
        key = "journal-tool-returned" if e.ok else "journal-tool-returned-failed"
        message = Message.of(key, tool=e.name, seconds=e.duration_s)
        tone = Tone.NORMAL if e.ok else Tone.WARNING
        return self._line(e, message, detail=e.output, tone=tone, tool=e.name, outcome=(e.ok, e.duration_s))

    def _tool_completed(self, e: ToolCompleted) -> Line:
        outcome = (e.ok, e.duration_s)
        if e.ok:
            message = Message.of("journal-tool-completed", tool=e.name, seconds=e.duration_s)
            return self._line(e, message, detail=e.output, tool=e.name, outcome=outcome)
        message = Message.of("journal-tool-failed", tool=e.name)
        return self._line(e, message, detail=e.output, tone=Tone.WARNING, tool=e.name, outcome=outcome)

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
        return self._line(e, message, people=[e.person], room=e.room)

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

    def _config_changed(self, e: ConfigChanged) -> Line:
        paths = Message.of("journal-detail-settings", paths=", ".join(e.changed_paths), count=len(e.changed_paths))
        line = self._by(e, e.by, "journal-config-changed", restored=_yes(e.restored is not None))
        return replace(line, detail_message=paths if e.changed_paths else None)

    def _by(self, event: Event, by: str, id: str, *, tone: Tone = Tone.NORMAL, **args: str) -> Line:
        """What a person did from the admin (`by` an account id), or someone from the command line."""
        cli = by == CLI
        return self._account(event, None if cli else by, id, tone=tone, via="cli" if cli else "admin", **args)

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
        room: str | None = None,
        tool: str | None = None,
        outcome: tuple[bool, float] | None = None,
        attachments: tuple[Attached, ...] = (),
    ) -> Line:
        if len(detail) > DETAIL_LIMIT:
            detail = detail[:DETAIL_LIMIT] + "…"
        return Line(
            at=event.at,
            kind=self._categories.get(type(event), Kind.OTHER),
            message=message,
            detail=detail,
            detail_message=detail_message,
            reason=reason,
            people=frozenset(p for p in people if p),
            channels=frozenset(a.channel for a in channels if a),
            tone=tone,
            room=room or _room(event),
            tool=tool,
            outcome=outcome,
            attachments=attachments,
        )
