"""Watching through the satellites from the admin: who may, by role and by the device's list, and what ends with
the admin session. The relay is a double; the real one is proven with aiortc in the satellites channel's tests."""

from pathlib import Path

from nestor.modules.accounts import Role
from nestor.modules.satellites import (
    VIDEO_CAPTURE,
    DeclaredCapability,
    Device,
    Manifest,
    MediaEnd,
    MediaSessionClosed,
    MediaSessions,
)
from nestor.testing.journal import MemoryBlobStore
from nestor.testing.satellites import SOFTWARE, FilmingRelay, pair_by_code

from ....harness import Harness

CAMERA = Manifest(
    Device("camera-entree", "raspberry-pi-zero", "entree"), (DeclaredCapability(VIDEO_CAPTURE),), software=SOFTWARE
)
JPEG = b"\xff\xd8\xff\xe0 a picture \xff\xd9"


async def watching(admin: Harness) -> MediaSessions:
    nestor = admin.nestor
    await pair_by_code(nestor.pairing, CAMERA)
    nestor.media = MediaSessions(nestor.journal, nestor.pairing, FilmingRelay(JPEG), MemoryBlobStore())
    return nestor.media


async def test_a_member_watches_only_the_cameras_listing_them_an_owner_every_one(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await watching(admin)
        await admin.account("lucie", Role.MEMBER, person="lucie")
        owner, member = await admin.api(), await admin.api("lucie")
        assert [d["id"] for d in (await owner.get("/api/v1/media/devices")).json()["devices"]] == ["camera-entree"]
        assert (await member.get("/api/v1/media/devices")).json()["devices"] == []
        refused = await member.post("/api/v1/satellites/camera-entree/media/snapshot")
        assert refused.status_code == 403 and refused.json()["error"]["code"] == "media_forbidden"

        listed = await owner.put("/api/v1/satellites/camera-entree/media/access", {"viewers": ["lucie"]})
        assert listed.status_code == 200
        picture = await member.post("/api/v1/satellites/camera-entree/media/snapshot")
        assert picture.content == JPEG and "entree-" in picture.headers["content-disposition"]


async def test_what_someone_watches_ends_when_they_sign_out(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await watching(admin)
        owner = await admin.api()
        opened = await owner.post(
            "/api/v1/satellites/camera-entree/media/sessions", {"purpose": "view", "sdp": "v=0", "type": "offer"}
        )
        assert opened.status_code == 200 and opened.json()["video"] is True
        assert (await owner.delete("/api/v1/session")).status_code == 204
        [closed] = await admin.nestor.journal.history(MediaSessionClosed)
        assert closed.reason is MediaEnd.SIGNED_OUT
