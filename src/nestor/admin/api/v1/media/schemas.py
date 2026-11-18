"""What the media routes take and send."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.core import PersonId
from nestor.modules.satellites import LiveSession, MediaAccess, Off, Offer, Privacy, Purpose, QuietHours


class MediaDeviceOut(BaseModel):
    """A device the caller may watch or call through."""

    id: str
    name: str | None
    room: str
    connected: bool
    can_view: bool  # it films, its camera films now, and the caller may watch it
    can_call: bool  # it hears and plays sound, and the caller may call through it
    off: Off | None  # why its camera does not film now

    @classmethod
    def of(cls, offer: Offer) -> "MediaDeviceOut":
        satellite = offer.satellite
        return cls(
            id=satellite.id,
            name=satellite.name,
            room=satellite.room,
            connected=offer.linked is not None,
            can_view=offer.view and offer.off is None,
            can_call=offer.call,
            off=offer.off,
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
    def of(cls, live: LiveSession) -> "MediaSessionOut":
        return cls(
            session_id=live.id,
            sdp=str(live.answer["sdp"]),
            type=str(live.answer["type"]),
            video=live.video,
            audio=live.audio,
            max_s=live.max_s,
        )


type Weekday = Annotated[int, Field(ge=0, le=6)]  # 0 Monday to 6 Sunday
type Clock = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]  # HH:MM


class QuietHoursIO(BaseModel):
    """A time slot when the camera does not film, in the household's time: from `start` to `end` (past midnight when
    `end` is not after `start`, a whole day when equal), starting on each of `days`."""

    days: list[Weekday] = Field(min_length=1, max_length=7)
    start: Clock
    end: Clock

    def to_domain(self) -> QuietHours:
        return QuietHours(tuple(sorted(set(self.days))), self.start, self.end)


class PrivacyIO(BaseModel):
    """When the camera does not film, besides its switch: nothing by default. `off_when_home`: while one of
    `home_people` is home (anyone of the household when empty), as Home Assistant sees it."""

    quiet: list[QuietHoursIO] = Field(default=[], max_length=16)
    off_when_home: bool = False
    home_people: list[str] = Field(default=[], max_length=64)

    def to_domain(self) -> Privacy:
        return Privacy(
            tuple(q.to_domain() for q in self.quiet),
            self.off_when_home,
            tuple(sorted(map(PersonId, set(self.home_people)))),
        )


class PrivacyOut(BaseModel):
    quiet: list[QuietHoursIO]
    off_when_home: bool
    home_people: list[PersonRef]

    @classmethod
    def of(cls, privacy: Privacy, people: People) -> "PrivacyOut":
        return cls(
            quiet=[QuietHoursIO(days=list(q.days), start=q.start, end=q.end) for q in privacy.quiet],
            off_when_home=privacy.off_when_home,
            home_people=[ref for p in privacy.home_people if (ref := people.ref(p))],
        )


class MediaAccessIn(BaseModel):
    """Who may watch the device or call through it besides the owners, whether its camera may film, and when it
    does not (`privacy`)."""

    viewers: list[str] = Field(default=[], max_length=64)
    callers: list[str] = Field(default=[], max_length=64)
    camera: bool = True
    privacy: PrivacyIO = PrivacyIO()


class MediaAccessOut(BaseModel):
    viewers: list[PersonRef]
    callers: list[PersonRef]
    camera: bool
    privacy: PrivacyOut

    @classmethod
    def of(cls, access: MediaAccess, people: People) -> "MediaAccessOut":
        return cls(
            viewers=[ref for p in sorted(access.viewers) if (ref := people.ref(p))],
            callers=[ref for p in sorted(access.callers) if (ref := people.ref(p))],
            camera=access.camera,
            privacy=PrivacyOut.of(access.privacy, people),
        )
