"""Media sessions: a person watches what a satellite films, or calls through one, from the admin.

Nothing leaves a device but in a session a person with the right opened, through the device's authenticated link
(`intent.media.open`): the device connects to the core, the only peer it ever has, and the core relays to the person
(`MediaRelay`, an adapter). Who may: an owner, or a person the device's `MediaAccess` lists (`viewers` to watch,
`callers` to call). Each session is journaled, ends at its longest duration and with the admin session that opened
it. A still picture (`snapshot`) is kept `SNAPSHOT_DAYS` days, then forgotten.
"""

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from nestor.core import Capability, Component, ContractError, PersonId, ProviderError, new_id, utc_now
from nestor.modules.journal import BlobStore, FileRef, Journal
from nestor.modules.satellites.events import (
    MediaEnd,
    MediaSessionClosed,
    MediaSessionOpened,
    SatelliteMediaAccessSet,
    SnapshotTaken,
)
from nestor.modules.satellites.service import Pairing
from nestor.modules.satellites.types import AUDIO_CAPTURE, AUDIO_PLAYBACK, VIDEO_CAPTURE, MediaAccess, Satellite

logger = logging.getLogger(__name__)

SNAPSHOT_DAYS = 7
CALL = frozenset({AUDIO_CAPTURE, AUDIO_PLAYBACK})  # both ways: what a call needs

type Ended = Callable[[str, MediaEnd], Awaitable[None]]


class Purpose(StrEnum):
    VIEW = "view"  # watch what it films
    CALL = "call"  # talk through it and hear the room, with its video when the person may watch too


@dataclass(frozen=True, slots=True)
class Viewer:
    """Who opens a session: their account, its person, whether they own the household, and the admin session it
    belongs to (it ends with it)."""

    account_id: str
    person: PersonId | None
    owner: bool
    signed_in: str


class MediaRefused(ContractError):
    """A session or a picture cannot be had. `reason`: `unknown` (no such device), `offline` (its link is down),
    `unable` (it was not allowed what this needs), `camera_off`, `forbidden` (not for this person)."""

    def __init__(self, reason: str, message: str) -> None:
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
class Opened:
    """A session that opened: the WebRTC answer for the person's browser, what it carries, how long at most."""

    session_id: str
    answer: Mapping[str, Any]
    video: bool
    audio: bool
    max_s: int


@dataclass(slots=True)
class LiveSession:
    id: str
    viewer: Viewer
    satellite: Satellite
    video: bool
    audio: bool
    max_s: int
    started: float = field(default_factory=time.monotonic)
    timer: asyncio.Task[None] | None = field(default=None, repr=False)


class MediaSessions(Component):
    name = "media-sessions"

    def __init__(
        self,
        journal: Journal,
        pairing: Pairing,
        relay: MediaRelay,
        blobs: BlobStore | None = None,
        *,
        view_max_s: int = 600,
        call_max_s: int = 1800,
    ) -> None:
        self.journal, self._pairing, self._relay, self._blobs = journal, pairing, relay, blobs
        self._max_s = {Purpose.VIEW: view_max_s, Purpose.CALL: call_max_s}
        self._live: dict[str, LiveSession] = {}
        relay.on_ended(self._ended)

    async def start(self) -> None:
        await self.forget_old_snapshots()

    async def close(self) -> None:
        for session_id in list(self._live):
            await self.close_session(session_id, MediaEnd.CLOSED)

    def sessions(self) -> list[LiveSession]:
        return list(self._live.values())

    def linked(self, device_id: str) -> frozenset[Capability] | None:
        """What the device's link was allowed, `None` while it is down."""
        return self._relay.linked(device_id)

    def may(self, satellite: Satellite, viewer: Viewer, purpose: Purpose) -> bool:
        """Whether `viewer` may watch (`VIEW`) or call through (`CALL`) the device: an owner always, a person only
        when the device lists them."""
        if viewer.owner:
            return True
        listed = satellite.access.viewers if purpose is Purpose.VIEW else satellite.access.callers
        return viewer.person is not None and viewer.person in listed

    async def set_access(self, device_id: str, access: MediaAccess, *, by: PersonId | None = None) -> Satellite:
        """Who may watch or call through the device besides its owners, and whether its camera may film. Sessions
        that the change no longer allows end at once."""
        self._satellite(device_id)
        await self.journal.publish(
            SatelliteMediaAccessSet(
                source=self.name,
                device_id=device_id,
                viewers=tuple(sorted(access.viewers)),
                callers=tuple(sorted(access.callers)),
                camera=access.camera,
                by=by,
            )
        )
        satellite = self._pairing.set_access(device_id, access)
        for live in [s for s in self._live.values() if s.satellite.id == device_id]:
            still = self.may(satellite, live.viewer, Purpose.CALL if live.audio else Purpose.VIEW)
            if not still or (live.video and not access.camera):
                await self.close_session(live.id, MediaEnd.SIGNED_OUT)
        return satellite

    async def open(self, device_id: str, purpose: Purpose, viewer: Viewer, offer: Mapping[str, Any]) -> Opened:
        """Open a session for `viewer` and answer their browser's WebRTC `offer`; `MediaRefused` says why not."""
        satellite = self._satellite(device_id)
        allowed = self._relay.linked(device_id)
        if allowed is None:
            raise MediaRefused("offline", f"{device_id} is not connected")
        if not self.may(satellite, viewer, purpose):
            raise MediaRefused("forbidden", f"not allowed to {purpose} {device_id}")
        can_film = VIDEO_CAPTURE in allowed and satellite.access.camera
        if purpose is Purpose.VIEW:
            if VIDEO_CAPTURE not in allowed:
                raise MediaRefused("unable", f"{device_id} does not film")
            if not satellite.access.camera:
                raise MediaRefused("camera_off", f"the camera of {device_id} is off")
            video, audio = True, False
        else:
            if not allowed >= CALL:
                raise MediaRefused("unable", f"{device_id} cannot both hear and play sound")
            video, audio = can_film and self.may(satellite, viewer, Purpose.VIEW), True
        live = LiveSession(new_id(), viewer, satellite, video, audio, self._max_s[purpose])
        self._live[live.id] = live
        await self.journal.publish(
            MediaSessionOpened(
                source=self.name,
                session_id=live.id,
                device_id=device_id,
                room=satellite.room,
                video=video,
                audio=audio,
                max_s=live.max_s,
                person=viewer.person,
                account_id=viewer.account_id,
            )
        )
        try:
            answer = await self._relay.start(
                live.id, device_id, video=video, audio=audio, max_s=live.max_s, offer=offer
            )
        except ProviderError as error:
            logger.warning("media session %s on %s could not open: %s", live.id, device_id, error)
            await self.close_session(live.id, MediaEnd.FAILED)
            raise MediaRefused("offline", f"{device_id} did not open the session") from None
        live.timer = asyncio.create_task(self._time_out(live), name=f"media session {live.id}")
        return Opened(live.id, answer, video, audio, live.max_s)

    async def close_session(self, session_id: str, reason: MediaEnd, *, by: Viewer | None = None) -> None:
        """End a session; `by` a person, only their own, or any for an owner."""
        live = self._live.get(session_id)
        if live is None or (by is not None and not by.owner and by.account_id != live.viewer.account_id):
            return
        del self._live[session_id]
        if live.timer is not None and live.timer is not asyncio.current_task():
            live.timer.cancel()
        await self._relay.stop(session_id)
        await self.journal.publish(
            MediaSessionClosed(
                source=self.name,
                session_id=session_id,
                device_id=live.satellite.id,
                room=live.satellite.room,
                duration_s=round(time.monotonic() - live.started, 1),
                reason=reason,
            )
        )

    async def signed_out(self, signed_in: str) -> None:
        """The admin session `signed_in` ended: its media sessions end with it."""
        for live in [s for s in self._live.values() if s.viewer.signed_in == signed_in]:
            await self.close_session(live.id, MediaEnd.SIGNED_OUT)

    async def snapshot(self, device_id: str, viewer: Viewer) -> FileRef:
        """A still picture of what the device films, for `viewer` (in the admin, or a person who asked the agent),
        who must be allowed to watch it; kept `SNAPSHOT_DAYS` days."""
        satellite = self._satellite(device_id)
        if not self.may(satellite, viewer, Purpose.VIEW):
            raise MediaRefused("forbidden", f"not allowed to view {device_id}")
        allowed = self._relay.linked(device_id)
        if allowed is None:
            raise MediaRefused("offline", f"{device_id} is not connected")
        if VIDEO_CAPTURE not in allowed:
            raise MediaRefused("unable", f"{device_id} does not film")
        if not satellite.access.camera:
            raise MediaRefused("camera_off", f"the camera of {device_id} is off")
        if self._blobs is None:
            raise MediaRefused("unable", "pictures cannot be kept here")
        try:
            jpeg = await self._relay.snapshot(device_id)
        except ProviderError as error:
            raise MediaRefused("offline", f"{device_id} gave no picture: {error}") from None
        file = FileRef(await self._blobs.put(jpeg, "image/jpeg"), f"{satellite.room}-{utc_now():%Y%m%d-%H%M%S}.jpg")
        await self.journal.publish(
            SnapshotTaken(
                source=self.name,
                device_id=device_id,
                room=satellite.room,
                file=file,
                person=viewer.person,
                account_id=viewer.account_id or None,
            )
        )
        return file

    async def forget_old_snapshots(self) -> None:
        """Delete the pictures taken more than `SNAPSHOT_DAYS` days ago."""
        if self._blobs is None:
            return
        older = utc_now() - timedelta(days=SNAPSHOT_DAYS)
        for taken in await self.journal.history(SnapshotTaken):
            if taken.at < older:
                with contextlib.suppress(KeyError):
                    await self._blobs.delete(taken.file.blob.digest)

    def _satellite(self, device_id: str) -> Satellite:
        found = next((s for s in self._pairing.satellites() if s.id == device_id), None)
        if found is None:
            raise MediaRefused("unknown", f"no satellite {device_id}")
        return found

    async def _time_out(self, live: LiveSession) -> None:
        await asyncio.sleep(live.max_s)
        await self.close_session(live.id, MediaEnd.TIMED_OUT)

    async def _ended(self, session_id: str, reason: MediaEnd) -> None:
        if session_id in self._live:
            await self.close_session(session_id, reason)
