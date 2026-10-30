"""Journal events as French lines: what happened, to whom, through which channel, and why.

Only the important events get a sentence; any other event is still listed under its type, so the
page never hides what the journal holds.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nestor.admin.presentation.capabilities import french_capability
from nestor.admin.presentation.reasons import french_reason, french_subject, french_task_status, french_watch_end
from nestor.core import ContractError, Event, PersonId
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


class Tone(StrEnum):
    NORMAL = "normal"
    DECISION = "decision"  # why the assistant spoke up
    WARNING = "warning"  # a failure worth a look


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    label: str
    events: tuple[type[Event], ...]

    @property
    def types(self) -> frozenset[str]:
        return frozenset(e.event_type for e in self.events)


CATEGORIES = (
    Category("conversation", "Conversations", (UserTurn, AssistantTurn, FallbackSpoken, AnswerCut)),
    Category("initiative", "Prises de parole", (DeliveryConsidered, Delivered, DeliveryFailed)),
    Category("tools", "Outils", (ToolCalled, ToolCompleted)),
    Category(
        "tasks",
        "Tâches",
        (TaskStarted, TaskAttached, TaskProgressed, TaskCancelRequested, TaskEnded, TaskDelivered),
    ),
    Category("watches", "Veilles", (WatchCreated, WatchTriggered, WatchEnded)),
    Category("memory", "Souvenirs", (MemoryRecorded, MemoryCorrected, MemoryForgotten)),
    Category("connections", "Connexions", (ConnectionCreated, ConnectionChanged, ConnectionRemoved)),
    Category("presence", "Présence", (PresenceChanged,)),
    Category(
        "satellites",
        "Satellites",
        (SatellitePairingRequested, SatellitePaired, SatelliteRevoked, SatelliteConnected, SatelliteDisconnected),
    ),
    Category("observations", "Observations", (PersonDetected, SpeechActivityObserved)),
)
OTHER = "Autres"

_FALLBACKS = {
    "model_unavailable": "modèle indisponible",
    "model_slow": "modèle trop lent",
    "recognition_unavailable": "reconnaissance vocale indisponible",
    "synthesis_unavailable": "synthèse vocale indisponible",
}
_CONNECTION_STATUS = {"connected": "connectée", "needs_reauth": "à réautoriser", "error": "en erreur"}


@dataclass(frozen=True, slots=True, kw_only=True)
class Line:
    at: datetime
    category: str
    title: str
    detail: str = ""
    reason: str = ""  # the decision's reason, shown prominently
    people: frozenset[PersonId] = field(default_factory=frozenset)
    channels: frozenset[str] = field(default_factory=frozenset)
    tone: Tone = Tone.NORMAL


class EventDescriber:
    def __init__(self, household: Household, assistant: str) -> None:
        self.household, self.assistant = household, assistant
        self._categories = {e: c.label for c in CATEGORIES for e in c.events}
        self._describers: Mapping[type[Event], Callable[..., Line]] = {
            UserTurn: self._user_turn,
            AssistantTurn: self._assistant_turn,
            FallbackSpoken: self._fallback,
            AnswerCut: self._cut,
            ToolCalled: self._tool_called,
            ToolCompleted: self._tool_completed,
            TaskStarted: self._task_started,
            TaskAttached: lambda e: self._line(e, f"Tâche {e.task_id} suivie chez l'exécutant"),
            TaskProgressed: lambda e: self._line(e, f"Tâche {e.task_id} : nouvelle étape", detail=e.step),
            TaskCancelRequested: lambda e: self._line(e, f"Arrêt demandé pour la tâche {e.task_id}"),
            TaskEnded: self._task_ended,
            TaskDelivered: lambda e: self._line(e, f"Résultat de la tâche {e.task_id} transmis", channels=[e.address]),
            DeliveryConsidered: self._considered,
            Delivered: lambda e: self._line(
                e, f"Message transmis — {french_subject(e.about)}", people=[e.person], channels=[e.address]
            ),
            DeliveryFailed: self._undeliverable,
            WatchCreated: self._watch_created,
            WatchTriggered: self._watch_triggered,
            WatchEnded: lambda e: self._line(e, f"Veille {e.watch_id} {french_watch_end(e.reason)}"),
            MemoryRecorded: lambda e: self._line(
                e, "Souvenir enregistré", detail=e.text, people=[e.about, e.told_by], channels=[e.learnt_in]
            ),
            MemoryCorrected: lambda e: self._line(e, "Souvenir corrigé", detail=e.text, people=[e.by]),
            MemoryForgotten: lambda e: self._line(e, "Souvenir oublié", people=[e.by]),
            ConnectionCreated: lambda e: self._line(e, f"Compte {e.account} connecté ({e.kind})", people=[e.owner]),
            ConnectionChanged: self._connection_changed,
            ConnectionRemoved: lambda e: self._line(e, f"Connexion {e.connection_id} supprimée"),
            PresenceChanged: self._presence,
            SatellitePairingRequested: lambda e: self._line(
                e,
                f"Le satellite {e.device.id} ({e.device.model}, pièce « {e.device.room} ») demande l'appairage",
                detail=f"Déclare : {_capabilities(e.capabilities)}",
            ),
            SatellitePaired: lambda e: self._line(
                e,
                f"Satellite {e.device.id} appairé (pièce « {e.device.room} »)",
                detail=f"Autorisé : {_capabilities(e.capabilities)}",
                people=[e.approved_by],
            ),
            SatelliteRevoked: lambda e: self._line(
                e, f"Satellite {e.device_id} révoqué", people=[e.revoked_by], tone=Tone.WARNING
            ),
            SatelliteConnected: lambda e: self._line(e, f"Satellite {e.device_id} connecté (pièce « {e.room} »)"),
            SatelliteDisconnected: lambda e: self._line(e, f"Satellite {e.device_id} déconnecté (pièce « {e.room} »)"),
            PersonDetected: self._person_detected,
            SpeechActivityObserved: lambda e: self._line(
                e,
                f"{'Parole détectée' if e.active else 'Fin de parole'} près de {e.device_id} (pièce « {e.room} »)",
            ),
        }

    def describe(self, entry: Entry) -> Line:
        try:
            event = entry.event()
        except ContractError:  # written by a plugin no longer installed, or by a newer version
            return Line(at=datetime.fromisoformat(str(entry.record["at"])), category=OTHER, title=entry.type)
        describer = self._describers.get(type(event))
        return describer(event) if describer else self._line(event, event.event_type)

    def name(self, person: PersonId | None) -> str:
        if person is None:
            return "quelqu'un d'inconnu"
        try:
            return self.household.person(person).name
        except ContractError:
            return str(person)

    # -- one sentence per event -------------------------------------------------------------------

    def _user_turn(self, e: UserTurn) -> Line:
        return self._line(e, f"{self.name(e.person)} a dit", detail=e.text, people=[e.person], channels=[e.address])

    def _assistant_turn(self, e: AssistantTurn) -> Line:
        title = f"{self.assistant} a répondu" + (" (interrompu)" if e.interrupted else "")
        return self._line(e, title, detail=e.text, channels=[e.address])

    def _fallback(self, e: FallbackSpoken) -> Line:
        title = f"Réponse de secours : {_FALLBACKS.get(e.reason, e.reason)}"
        return self._line(e, title, channels=[e.address], tone=Tone.WARNING)

    def _cut(self, e: AnswerCut) -> Line:
        return self._line(e, "Réponse coupée par la personne", detail=f"Entendu : {e.heard}")

    def _tool_called(self, e: ToolCalled) -> Line:
        arguments = json.dumps(dict(e.arguments), ensure_ascii=False, default=str)
        return self._line(e, f"Outil {e.name} appelé", detail=arguments, people=[e.person], channels=[e.address])

    def _tool_completed(self, e: ToolCompleted) -> Line:
        if e.ok:
            return self._line(e, f"Outil {e.name} terminé en {e.duration_s:.1f} s", detail=e.output)
        return self._line(e, f"Outil {e.name} en échec", detail=e.output, tone=Tone.WARNING)

    def _task_started(self, e: TaskStarted) -> Line:
        return self._line(
            e,
            f"Tâche {e.task_id} confiée à {e.executor}",
            detail=e.objective,
            people=[e.requested_by],
            channels=[e.origin],
        )

    def _task_ended(self, e: TaskEnded) -> Line:
        title = f"Tâche {e.task_id} {french_task_status(e.status)} ({e.duration_s:.0f} s)"
        tone = Tone.WARNING if e.status == "failed" else Tone.NORMAL
        return self._line(e, title, detail=e.error or e.result or "", tone=tone)

    def _considered(self, e: DeliveryConsidered) -> Line:
        ways = []
        if e.spoken:
            ways.append(f"à voix haute sur {e.spoken}")
        if e.written:
            ways.append(f"par écrit sur {e.written}")
        plan = " puis ".join(ways) if ways else "nulle part"
        return self._line(
            e,
            f"Décision de parler à {self.name(e.person)} — {french_subject(e.about)}",
            reason=french_reason(e.reason),
            detail=f"Prévu : {plan}",
            people=[e.person],
            channels=[e.spoken, e.written],
            tone=Tone.DECISION,
        )

    def _undeliverable(self, e: DeliveryFailed) -> Line:
        tried = ", ".join(str(a) for a in e.tried) or "aucun canal disponible"
        return self._line(
            e,
            f"Message non transmis — {french_subject(e.about)}",
            detail=f"Essayé : {tried}",
            people=[e.person],
            channels=e.tried,
            tone=Tone.WARNING,
        )

    def _watch_created(self, e: WatchCreated) -> Line:
        detail = f"Mots-clés : {', '.join(e.keywords)}" if e.keywords else ""
        return self._line(e, f"Veille créée : {e.what}", detail=detail, people=[e.owner], channels=[e.created_in])

    def _watch_triggered(self, e: WatchTriggered) -> Line:
        title = f"Veille {e.watch_id} déclenchée par « {e.item_title} »" + (" — urgent" if e.urgent else "")
        return self._line(e, title, detail=e.summary)

    def _connection_changed(self, e: ConnectionChanged) -> Line:
        status = _CONNECTION_STATUS.get(e.status, e.status)
        tone = Tone.NORMAL if e.status == "connected" else Tone.WARNING
        return self._line(e, f"Connexion {e.connection_id} {status}", detail=e.reason, tone=tone)

    def _presence(self, e: PresenceChanged) -> Line:
        name = self.name(e.person)
        if e.home is False:
            where = "n'est plus à la maison"
        elif e.room:
            where = f"est dans la pièce « {e.room} »"
        elif e.home:
            where = "est à la maison"
        else:
            where = "n'est plus localisé·e"
        return self._line(e, f"{name} {where}", people=[e.person])

    def _person_detected(self, e: PersonDetected) -> Line:
        seen = "personne vue" if e.count == 1 else "personnes vues"
        title = f"{e.count} {seen} par {e.device_id} (pièce « {e.room} »)"
        return self._line(e, title, detail=f"Confiance : {e.confidence:.0%}")

    def _line(
        self,
        event: Event,
        title: str,
        *,
        detail: str = "",
        reason: str = "",
        people: Iterable[PersonId | None] = (),
        channels: Iterable[Address | None] = (),
        tone: Tone = Tone.NORMAL,
    ) -> Line:
        if len(detail) > DETAIL_LIMIT:
            detail = detail[:DETAIL_LIMIT] + "…"
        return Line(
            at=event.at,
            category=self._categories.get(type(event), OTHER),
            title=title,
            detail=detail,
            reason=reason,
            people=frozenset(p for p in people if p),
            channels=frozenset(a.channel for a in channels if a),
            tone=tone,
        )


def _capabilities(names: tuple[str, ...]) -> str:
    return ", ".join(french_capability(n) for n in names) or "rien"
