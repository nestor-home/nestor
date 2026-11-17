"""`look`: the agent looks at a room through a camera there, for a person who may see it and asks from their
account; the picture goes to the model only."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest

from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import Made, ToolContext, ToolFailed
from nestor.modules.identity import Identified, Speaker
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    VIDEO_CAPTURE,
    DeclaredCapability,
    Device,
    LookTools,
    Manifest,
    MediaAccess,
    MediaSessions,
    Pairing,
    Purpose,
    Viewer,
)
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog
from nestor.testing.satellites import SOFTWARE, FilmingRelay, pair_by_code

CAMERA = Manifest(Device("camera-salon", "pi", "salon"), (DeclaredCapability(VIDEO_CAPTURE),), software=SOFTWARE)
JPEG = b"\xff\xd8 the living room \xff\xd9"
MATHIS, LEA = PersonId("mathis"), PersonId("lea")
ROLES = {  # what each person's account lets them do: Mathis owns the household, Léa is a member
    MATHIS: Viewer(account_id="a-mathis", person=MATHIS, may=frozenset(Purpose), everywhere=frozenset(Purpose)),
    LEA: Viewer(account_id="a-lea", person=LEA, may=frozenset(Purpose)),
}
WRITING = Address("telegram", "mathis")


def asked(person: PersonId, by: Identified = Identified.ACCOUNT) -> ToolContext:
    return ToolContext(address=WRITING, speaker=Speaker(person, by))


@asynccontextmanager
async def home(*, camera: bool = True) -> AsyncGenerator[tuple[LookTools, Pairing, FilmingRelay]]:
    journal = Journal(MemoryEventLog())
    pairing = Pairing(journal)
    relay = FilmingRelay(JPEG)
    async with pairing:
        if camera:
            await pair_by_code(pairing, CAMERA)
        yield LookTools(MediaSessions(journal, pairing, relay, MemoryBlobStore()), ROLES.get), pairing, relay


async def test_someone_who_may_see_the_room_gets_a_picture_for_the_model_only() -> None:
    async with home() as (look, _, _):
        made = await look.look({"room": "salon"}, asked(MATHIS))
    assert isinstance(made, Made) and made.files == ()
    [picture] = made.seen
    assert (picture.data, picture.media_type) == (JPEG, "image/jpeg")


@pytest.mark.parametrize("by", [Identified.VOICE, Identified.SAID, Identified.UNKNOWN])
async def test_only_an_account_vouches_for_who_looks(by: Identified) -> None:
    async with home() as (look, _, relay):
        with pytest.raises(ToolFailed, match="own account"):
            await look.look({"room": "salon"}, asked(MATHIS, by))
    assert relay.pictures == 0


async def test_a_member_looks_only_at_a_room_whose_camera_lists_them() -> None:
    async with home() as (look, pairing, relay):
        with pytest.raises(ToolFailed, match="may not see"):
            await look.look({"room": "salon"}, asked(LEA))
        assert relay.pictures == 0
        await pairing.set_access(CAMERA.device.id, MediaAccess(viewers=frozenset({LEA})))
        made = await look.look({"room": "salon"}, asked(LEA))
    assert isinstance(made, Made) and made.seen


async def test_the_tool_is_offered_for_the_rooms_a_camera_films_only() -> None:
    async with home() as (look, _, _):
        [tool] = look.tools()
        assert tool.spec.parameters["properties"]["room"]["enum"] == ["salon"]  # ty: ignore[not-subscriptable]
    async with home(camera=False) as (look, _, _):
        assert look.tools() == ()
