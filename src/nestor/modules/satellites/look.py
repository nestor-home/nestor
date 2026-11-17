"""`look`: the agent takes a picture of a room through a satellite that films there and looks at it, for a person
who may see that room.

The same rights as in the admin (`MediaSessions`): their account's role, and the device's list. Only an account
vouches for who asks (a voice or a name only personalises): asked aloud or by someone the channel does not
authenticate, the agent says to ask from their own account. The picture is kept as any other (`SnapshotTaken`,
`SNAPSHOT_DAYS` days) and is not sent to anyone: the model looks at it and answers.
"""

from collections.abc import Callable, Mapping, Sequence

from nestor.core import PersonId
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Made, Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.identity import Identified
from nestor.modules.satellites.media import MediaRefused, MediaSessions, Viewer
from nestor.modules.satellites.types import VIDEO_CAPTURE

TIMEOUT_S = 20.0  # a device answers a picture within 10 s (`SNAPSHOT_WAIT_S`)

type Viewers = Callable[[PersonId], Viewer | None]  # what a person's account lets them do, `None` without one


class LookTools(ToolProvider):
    name = "look"

    def __init__(self, media: MediaSessions, viewer: Viewers) -> None:
        self._media, self._viewer = media, viewer

    def tools(self) -> Sequence[Tool]:
        rooms = sorted({s.room for s in self._media.devices() if VIDEO_CAPTURE in s.capabilities})
        if not rooms:
            return ()
        spec = ToolSpec(
            "look",
            "Take a picture of a room now, through a camera there, and look at it: to answer what is happening "
            "there, whether a light is on, who is there. Only for a person who may see that room, asking from "
            "their own account. The picture goes to you only; describe what matters.",
            {
                "type": "object",
                "properties": {"room": {"type": "string", "enum": rooms, "description": "the room to look at"}},
                "required": ["room"],
            },
        )
        return (Tool(spec=spec, run=self.look, risk=Risk.READ, timeout_s=TIMEOUT_S),)

    async def look(self, arguments: Mapping[str, object], context: ToolContext) -> Made:
        room = str(arguments.get("room", ""))
        if context.speaker.by is not Identified.ACCOUNT or context.person is None:
            raise ToolFailed(
                "looking through a camera needs to know for sure who asks: they ask from their own account, in writing"
            )
        viewer = self._viewer(context.person)
        if viewer is None:
            raise ToolFailed(f"{context.person} has no account that may see the cameras")
        cameras = [o for o in self._media.offers(viewer) if o.view and o.satellite.room == room]
        if not cameras:
            raise ToolFailed(f"{context.person} may not see {room}, or no camera films there")
        connected = [o for o in cameras if o.linked is not None] or cameras
        try:
            taken, jpeg = await self._media.snapshot(connected[0].satellite.id, viewer)
        except MediaRefused as refused:
            raise ToolFailed(f"no picture of {room}: {refused}") from None
        picture = Attachment(kind=AttachmentKind.IMAGE, data=jpeg, media_type="image/jpeg", name=taken.name)
        return Made({"room": room, "picture": "taken now, attached for you to look at"}, seen=(picture,))
