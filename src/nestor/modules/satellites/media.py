"""Media sessions: a person watches what a satellite films, or calls through one, from the admin.

Nothing leaves a device but in a session a person with the right opened, through the device's authenticated link
(`intent.media.open`): the device connects to the core, the only peer it ever has, and the core relays to the person
(`MediaRelay`, an adapter). Who may: someone whose role lets them on every device, or a person the device's
`MediaAccess` lists (`viewers` to watch, `callers` to call). Each session is journaled, ends at its longest duration,
with the admin session that opened it, and as soon as its person may no longer do it. A still picture (`snapshot`) is
kept `SNAPSHOT_DAYS` days, then forgotten.
"""

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from nestor.core import Capability, Component, ContractError, PersonId, ProviderError, new_id, utc_now
from nestor.modules.journal import BlobStore, FileRef, Journal
from nestor.modules.satellites.events import MediaEnd, MediaSessionClosed, MediaSessionOpened, SnapshotTaken
from nestor.modules.satellites.service import Pairing
from nestor.modules.satellites.types import AUDIO, VIDEO_CAPTURE, Purpose, Satellite

logger = logging.getLogger(__name__)

SNAPSHOT_DAYS = 7
CHECK_S = 5.0  # how often each session's person is checked again (signed out, role or access changed)
DAY_S = 86_400.0

type Ended = Callable[[str, MediaEnd], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Viewer:
    """Who opens a session: their account and person, what their role lets them do on the devices that list them
    (`may`) and on every device (`everywhere`, within `may`). `now` gives who they are now (their role may have
    changed), `None` once the admin session they opened it from ended; without, they stay as they are."""

    account_id: str | None
    person: PersonId | None
    may: frozenset[Purpose]
    everywhere: frozenset[Purpose] = frozenset()
    now: Callable[[], "Viewer | None"] | None = field(default=None, compare=False, repr=False)

    def current(self) -> "Viewer | None":
        return self.now() if self.now is not None else self


class Refusal(StrEnum):
    UNKNOWN = "unknown"  # no such device
    OFFLINE = "offline"  # its link is down, or it did not answer
    UNABLE = "unable"  # it was not allowed what this needs
    CAMERA_OFF = "camera_off"
    FORBIDDEN = "forbidden"  # not for this person


class MediaRefused(ContractError):
    """A session or a picture cannot be had, and why (`reason`)."""

    def __init__(self, reason: Refusal, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class MediaRelay(ABC):
    """The media path of linked devices (an adapter): it asks a device for a session over its link, takes the
    device's connection, relays it to the person's, and ends both."""

    @abstractmethod
    def linked(self, device_id: str) -> frozenset[Capability] | None:
        """What the device's link was allowed (`welcome`), `None` when its link is down."""

    @abstractmethod
    async def start(
        self, session_id: str, device_id: str, *, video: bool, audio: bool, max_s: int, offer: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Open the session on the device, answer the person's WebRTC `offer` (`{sdp, type}`) with what it relays;
        `ProviderError` when the device does not take it."""

    @abstractmethod
    async def stop(self, session_id: str) -> None:
        """End the session on both sides; nothing when it ended already."""

    @abstractmethod
    async def snapshot(self, device_id: str) -> bytes:
        """A still picture, JPEG, from the device; `ProviderError` when it gives none in time."""

    @abstractmethod
    def on_ended(self, ended: Ended) -> None:
        """`ended` hears of a session that ended on the device's side (it left, its connection failed)."""


@dataclass(frozen=True, slots=True)
class Offer:
    """A device a person may watch (`view`) or call through (`call`); `linked`: what its link was allowed, `None`
    while it is down."""

    satellite: Satellite
    linked: frozenset[Capability] | None
    view: bool
    call: bool


@dataclass(slots=True)
class LiveSession:
    """A session that opened: the WebRTC answer for the person's browser, what it carries, how long at most."""

    id: str
    viewer: Viewer
    device_id: str
    room: str
    purpose: Purpose
    video: bool
    max_s: int
    answer: Mapping[str, Any] = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)
    timer: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def audio(self) -> bool:
        return self.purpose is Purpose.CALL


class MediaSessions(Component):
    name = "media-sessions"

    def __init__(
        self,
        journal: Journal,
        pairing: Pairing,
        relay: MediaRelay,
        blobs: BlobStore,
        *,
        view_max_s: int = 600,
        call_max_s: int = 1800,
        check_s: float = CHECK_S,
    ) -> None:
        self.journal, self._pairing, self._relay, self._blobs = journal, pairing, relay, blobs
        self._max_s = {Purpose.VIEW: view_max_s, Purpose.CALL: call_max_s}
        self._check_s = check_s
        self._live: dict[str, LiveSession] = {}
        self._tasks: list[asyncio.Task[None]] = []
        relay.on_ended(self._ended)

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._checking(), name="media sessions: who may"),
            asyncio.create_task(self._forgetting(), name="media sessions: old pictures"),
        ]

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for session_id in list(self._live):
            await self.close_session(session_id, MediaEnd.CLOSED)

    def may(self, satellite: Satellite, viewer: Viewer, purpose: Purpose) -> bool:
        """Whether `viewer` may watch (`VIEW`) or call through (`CALL`) the device: their role lets them, on every
        device or on those that list their person."""
        if purpose not in viewer.may:
            return False
        if purpose in viewer.everywhere:
            return True
        listed = satellite.access.viewers if purpose is Purpose.VIEW else satellite.access.callers
        return viewer.person is not None and viewer.person in listed

    def offers(self, viewer: Viewer) -> list[Offer]:
        """The devices `viewer` may watch or call through, connected or not."""
        found = []
        for satellite in self._pairing.satellites():
            linked = self._relay.linked(satellite.id)
            can = satellite.capabilities if linked is None else linked
            view = VIDEO_CAPTURE in can and self.may(satellite, viewer, Purpose.VIEW)
            call = can >= AUDIO and self.may(satellite, viewer, Purpose.CALL)
            if view or call:
                found.append(Offer(satellite, linked, view, call))
        return found

    async def open(self, device_id: str, purpose: Purpose, viewer: Viewer, offer: Mapping[str, Any]) -> LiveSession:
        """Open a session for `viewer` and answer their browser's WebRTC `offer`; `MediaRefused` says why not."""
        satellite, linked = self._ready(device_id, viewer, purpose)
        video = purpose is Purpose.VIEW or (VIDEO_CAPTURE in linked and self._films(satellite, viewer))
        live = LiveSession(new_id(), viewer, device_id, satellite.room, purpose, video, self._max_s[purpose])
        self._live[live.id] = live
        await self.journal.publish(
            MediaSessionOpened(
                source=self.name,
                session_id=live.id,
                device_id=device_id,
                room=live.room,
                video=video,
                audio=live.audio,
                max_s=live.max_s,
                person=viewer.person,
                account_id=viewer.account_id,
            )
        )
        try:
            live.answer = await self._relay.start(
                live.id, device_id, video=video, audio=live.audio, max_s=live.max_s, offer=offer
            )
        except ProviderError as error:
            logger.warning("media session %s on %s could not open: %s", live.id, device_id, error)
            await self.close_session(live.id, MediaEnd.FAILED)
            raise MediaRefused(Refusal.OFFLINE, f"{device_id} did not open the session") from None
        except BaseException:  # a bad offer, or the person left while it opened: nothing stays behind
            await self.close_session(live.id, MediaEnd.FAILED)
            raise
        live.timer = asyncio.create_task(self._time_out(live), name=f"media session {live.id}")
        return live

    async def close_session(self, session_id: str, reason: MediaEnd, *, by: Viewer | None = None) -> None:
        """End a session; `by` a person, only their own, or any of a kind their role allows on every device."""
        live = self._live.get(session_id)
        if live is None:
            return
        if by is not None and by.account_id != live.viewer.account_id and live.purpose not in by.everywhere:
            return
        del self._live[session_id]
        if live.timer is not None and live.timer is not asyncio.current_task():
            live.timer.cancel()
        try:
            await self._relay.stop(session_id)
        finally:  # ended for the household even when the connection would not close cleanly
            await self.journal.publish(
                MediaSessionClosed(
                    source=self.name,
                    session_id=session_id,
                    device_id=live.device_id,
                    room=live.room,
                    duration_s=round(time.monotonic() - live.started, 1),
                    reason=reason,
                )
            )

    async def check(self) -> None:
        """End at once the sessions whose person signed out, or may no longer do what they do (their role, or
        the device's access, changed); also run every `check_s` seconds."""
        for live in list(self._live.values()):
            viewer = live.viewer.current()
            if viewer is None:
                await self.close_session(live.id, MediaEnd.SIGNED_OUT)
            elif not self._still(live, viewer):
                await self.close_session(live.id, MediaEnd.ACCESS_CHANGED)

    async def snapshot(self, device_id: str, viewer: Viewer) -> tuple[FileRef, bytes]:
        """A still picture of what the device films, for `viewer`, who must be allowed to watch it: where it is
        kept (`SNAPSHOT_DAYS` days) and its JPEG."""
        satellite, _ = self._ready(device_id, viewer, Purpose.VIEW)
        try:
            jpeg = await self._relay.snapshot(device_id)
        except ProviderError as error:
            raise MediaRefused(Refusal.OFFLINE, f"{device_id} gave no picture: {error}") from None
        file = FileRef(await self._blobs.put(jpeg, "image/jpeg"), f"{satellite.room}-{utc_now():%Y%m%d-%H%M%S}.jpg")
        await self.journal.publish(
            SnapshotTaken(
                source=self.name,
                device_id=device_id,
                room=satellite.room,
                file=file,
                person=viewer.person,
                account_id=viewer.account_id,
            )
        )
        return file, jpeg

    async def forget_old_snapshots(self, since: datetime | None = None) -> datetime:
        """Delete the pictures taken more than `SNAPSHOT_DAYS` days ago, from `since` on (those before were
        forgotten already); where the next pass starts."""
        older = utc_now() - timedelta(days=SNAPSHOT_DAYS)
        for taken in await self.journal.history(SnapshotTaken, since=since):
            if taken.at < older:
                with contextlib.suppress(KeyError):
                    await self._blobs.delete(taken.file.blob.digest)
        return older

    def _ready(self, device_id: str, viewer: Viewer, purpose: Purpose) -> tuple[Satellite, frozenset[Capability]]:
        """The device and what its link was allowed, when `viewer` may do `purpose` with it now."""
        satellite = self._pairing.satellite(device_id)
        if satellite is None:
            raise MediaRefused(Refusal.UNKNOWN, f"no satellite {device_id}")
        if not self.may(satellite, viewer, purpose):
            raise MediaRefused(Refusal.FORBIDDEN, f"not allowed to {purpose} {device_id}")
        linked = self._relay.linked(device_id)
        if linked is None:
            raise MediaRefused(Refusal.OFFLINE, f"{device_id} is not connected")
        if purpose is Purpose.VIEW:
            if VIDEO_CAPTURE not in linked:
                raise MediaRefused(Refusal.UNABLE, f"{device_id} does not film")
            if not satellite.access.camera:
                raise MediaRefused(Refusal.CAMERA_OFF, f"the camera of {device_id} is off")
        elif not linked >= AUDIO:
            raise MediaRefused(Refusal.UNABLE, f"{device_id} cannot both hear and play sound")
        return satellite, linked

    def _films(self, satellite: Satellite, viewer: Viewer) -> bool:
        """Whether the device's camera may film for `viewer` (a call carries video only then)."""
        return satellite.access.camera and self.may(satellite, viewer, Purpose.VIEW)

    def _still(self, live: LiveSession, viewer: Viewer) -> bool:
        satellite = self._pairing.satellite(live.device_id)
        if satellite is None or not self.may(satellite, viewer, live.purpose):
            return False
        return not live.video or self._films(satellite, viewer)

    async def _checking(self) -> None:
        while True:
            await asyncio.sleep(self._check_s)
            try:
                await self.check()
            except Exception:
                logger.exception("media sessions: checking who may failed")

    async def _forgetting(self) -> None:
        since: datetime | None = None
        while True:
            try:
                since = await self.forget_old_snapshots(since)
            except Exception:
                logger.exception("media sessions: forgetting old pictures failed")
            await asyncio.sleep(DAY_S)

    async def _time_out(self, live: LiveSession) -> None:
        await asyncio.sleep(live.max_s)
        await self.close_session(live.id, MediaEnd.TIMED_OUT)

    async def _ended(self, session_id: str, reason: MediaEnd) -> None:
        await self.close_session(session_id, reason)
