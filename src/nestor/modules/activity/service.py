"""The activity monitor: adds up what runs into one state, and wakes whoever waits for a change."""

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.core import Component, utc_now
from nestor.modules.activity.types import Activity, AgentActivity
from nestor.modules.cognition.delegation import TaskEnded, TaskStarted
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.conversation import LiveReplies, ReplyPhase
from nestor.modules.initiative import QuietHours
from nestor.modules.journal import Journal, Subscription
from nestor.modules.satellites import SatelliteDisconnected, SpeechActivityObserved


class ActivityMonitor(Component):
    """What the agent is doing right now.

    - listening: a satellite said it hears someone (until it says it no longer does, or disconnects);
    - speaking / thinking: an answer is being produced, its words already coming out or not yet (the
      playback of the last words on a speaker is not known: speaking ends when the text is complete);
    - working: delegated tasks are running; sleeping: within the quiet hours; idle otherwise.

    `changes()` gives an event set at the next change, the turn of the quiet hours included.
    """

    name = "activity"

    def __init__(
        self,
        journal: Journal,
        replies: LiveReplies,
        tasks: TaskManager,
        *,
        quiet_hours: QuietHours | None = None,
        timezone: str = "Europe/Paris",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal, self.replies, self.tasks = journal, replies, tasks
        self.quiet_hours, self.timezone, self.clock = quiet_hours, ZoneInfo(timezone), clock
        self._heard: dict[str, str] = {}  # device id → room, while it hears someone
        self._changed = asyncio.Event()
        self._last: AgentActivity | None = None
        self._subscription: Subscription | None = None
        self._worker: asyncio.Task[None] | None = None
        self._unlisten: Callable[[], None] | None = None

    async def start(self) -> None:
        self._subscription = self.journal.subscribe(
            SpeechActivityObserved, SatelliteDisconnected, TaskStarted, TaskEnded
        )
        self._unlisten = self.replies.listen(self._refresh)
        self._worker = asyncio.create_task(self._follow(self._subscription), name="activity")
        self._refresh()

    async def close(self) -> None:
        if self._unlisten is not None:
            self._unlisten()
            self._unlisten = None
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def current(self) -> AgentActivity:
        return self._refresh()

    def changes(self) -> asyncio.Event:
        """Set at the next change; take it before reading `current()` so that none is missed."""
        return self._changed

    def _refresh(self) -> AgentActivity:
        now = self.clock()
        phases = self.replies.phases()
        tasks = len(self.tasks.running())
        quiet = self.quiet_hours is not None and self.quiet_hours.contains(now.astimezone(self.timezone).time())
        if self._heard:
            state = Activity.LISTENING
        elif ReplyPhase.SPEAKING in phases:
            state = Activity.SPEAKING
        elif phases:
            state = Activity.THINKING
        elif tasks:
            state = Activity.WORKING
        else:
            state = Activity.SLEEPING if quiet else Activity.IDLE
        last = self._last
        activity = AgentActivity(
            state=state,
            since=last.since if last is not None and last.state is state else now,
            replies=len(phases),
            tasks=tasks,
            listening_rooms=tuple(sorted(set(self._heard.values()))),
            quiet=quiet,
        )
        if not activity.same_as(last):
            self._last = activity
            self._changed.set()
            self._changed = asyncio.Event()
        return activity

    async def _follow(self, subscription: Subscription) -> None:
        while True:
            try:
                event = await subscription.next(self._until_quiet_turns())
            except StopAsyncIteration:
                return
            except TimeoutError:
                event = None  # the quiet hours begin or end
            if isinstance(event, SpeechActivityObserved):
                if event.active:
                    self._heard[event.device_id] = event.room
                else:
                    self._heard.pop(event.device_id, None)
            elif isinstance(event, SatelliteDisconnected):
                self._heard.pop(event.device_id, None)
            self._refresh()

    def _until_quiet_turns(self) -> float | None:
        """Seconds until the quiet hours begin or end; `None` without quiet hours."""
        if self.quiet_hours is None:
            return None
        local = self.clock().astimezone(self.timezone)
        waits = []
        for moment in (self.quiet_hours.start, self.quiet_hours.end):
            turn = local.replace(hour=moment.hour, minute=moment.minute, second=0, microsecond=0)
            if turn <= local:
                turn += timedelta(days=1)
            waits.append((turn - local).total_seconds())
        return min(waits) + 0.01  # just past the turn: `contains` then says the new state
