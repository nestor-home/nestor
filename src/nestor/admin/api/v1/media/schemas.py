"""What the media routes take and send."""

from typing import Literal

from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.modules.satellites import VIDEO_CAPTURE, MediaAccess, Opened, Purpose, Satellite
from nestor.modules.satellites.media import CALL


class MediaDeviceOut(BaseModel):
    """A device the caller may watch or call through."""

    id: str
    name: str | None
    room: str
    connected: bool
    can_view: bool  # it films, its camera is on, and the caller may watch it
    can_call: bool  # it hears and plays sound, and the caller may call through it

    @classmethod
    def of(cls, satellite: Satellite, allowed: frozenset[str] | None, *, view: bool, call: bool) -> "MediaDeviceOut":
        films = VIDEO_CAPTURE in (satellite.capabilities if allowed is None else allowed)
        return cls(
            id=satellite.id,
            name=satellite.name,
            room=satellite.room,
            connected=allowed is not None,
            can_view=view and films and satellite.access.camera,
            can_call=call and (satellite.capabilities if allowed is None else allowed) >= CALL,
        )


class MediaDevicesOut(BaseModel):
    available: bool  # media can be relayed here (the `media` extra)
    devices: list[MediaDeviceOut]


class MediaOfferIn(BaseModel):
    """The browser's WebRTC offer for a session: to watch (`view`), or to call (`call`)."""

    purpose: Purpose
    sdp: str = Field(max_length=100_000)
    type: Literal["offer"]


class MediaSessionOut(BaseModel):
    """The session that opened: the WebRTC answer, what it carries, how long at most."""

    session_id: str
    sdp: str
    type: str
    video: bool
    audio: bool
    max_s: int

    @classmethod
    def of(cls, opened: Opened) -> "MediaSessionOut":
        return cls(
            session_id=opened.session_id,
            sdp=str(opened.answer["sdp"]),
            type=str(opened.answer["type"]),
            video=opened.video,
            audio=opened.audio,
            max_s=opened.max_s,
        )


class MediaAccessIn(BaseModel):
    """Who may watch the device or call through it besides the owners, and whether its camera may film."""

    viewers: list[str] = Field(default=[], max_length=64)
    callers: list[str] = Field(default=[], max_length=64)
    camera: bool = True


class MediaAccessOut(BaseModel):
    viewers: list[PersonRef]
    callers: list[PersonRef]
    camera: bool

    @classmethod
    def of(cls, access: MediaAccess, people: People) -> "MediaAccessOut":
        return cls(
            viewers=[ref for p in sorted(access.viewers) if (ref := people.ref(p))],
            callers=[ref for p in sorted(access.callers) if (ref := people.ref(p))],
            camera=access.camera,
        )
