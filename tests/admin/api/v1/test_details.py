"""One resource at a time, and what each says about its state: why a connection is broken, since when
someone is where they are, when a task ended, when an account was last seen."""

import asyncio
from datetime import timedelta
from pathlib import Path

from nestor.core import PersonId, utc_now
from nestor.core.i18n import Message
from nestor.modules.accounts import Role
from nestor.modules.channels import Address, Attachment, AttachmentKind
from nestor.modules.cognition import Outcome, TaskEnded
from nestor.modules.connectors import Status
from nestor.modules.initiative import Watch
from nestor.modules.satellites import Device, Manifest
from nestor.testing.satellites import SOFTWARE, pair_by_code

from ...harness import Harness

TELEGRAM = Address("telegram", "42")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


async def test_a_broken_connection_says_why_in_the_readers_language(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        connections = admin.nestor.connections
        assert connections
        connection = await connections.connect("imap", MATHIS, {"server": "s", "password": "p"})
        api = await admin.api()
        assert (await api.get(f"/api/v1/connections/{connection.id}")).json()["status_reason"] is None
        await connections._mark(connection, Status.NEEDS_REAUTH, Message.of("connection-refresh-refused"))
        reason = (await api.get(f"/api/v1/connections/{connection.id}")).json()["status_reason"]
        assert reason["message"] == {"id": "connection-refresh-refused", "args": {}}
        assert reason["text"].startswith("Accès révoqué ou expiré")
        await connections.configure(connection.id, confirm_writes=False)
        assert connections.connections[connection.id].status_reason, "changing a setting keeps the reason"


async def test_the_files_a_task_handed_back_download_from_it_for_who_reaches_it(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        nestor = admin.nestor
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        task = await nestor.tasks.delegate("Le devis en PDF", origin=TELEGRAM, requested_by=MATHIS)
        while not admin.remote.runs:
            await asyncio.sleep(0.01)
        made = Attachment(kind=AttachmentKind.FILE, data=b"%PDF-1.7 devis", media_type="application/pdf")
        admin.remote.finish(next(iter(admin.remote.runs)), Outcome.completed("Le devis est prêt.", files=(made,)))
        while not await nestor.journal.history(TaskEnded):
            await asyncio.sleep(0.01)
        owner, guest = await admin.api(), await admin.api("mathilde")

        listed = (await owner.get(f"/api/v1/tasks/{task.id}")).json()["files"]
        assert listed == [{"index": 0, "kind": "file", "media_type": "application/pdf", "size": 14}]
        got = await owner.get(f"/api/v1/tasks/{task.id}/files/0")
        assert (got.status_code, got.content, got.headers["content-type"]) == (
            200,
            b"%PDF-1.7 devis",
            "application/octet-stream",
        ), "downloaded, never shown in place"
        assert (await owner.get(f"/api/v1/tasks/{task.id}/files/1")).status_code == 404
        assert (await guest.get(f"/api/v1/tasks/{task.id}/files/0")).json()["error"]["code"] == "task_unknown"


async def test_people_say_since_when_they_are_where_they_are(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        arrived = utc_now() - timedelta(hours=2)
        admin.presence.set("mathis", home=True, room="salon", since=arrived)
        api = await admin.api()
        mathis = (await api.get("/api/v1/household/people/mathis")).json()
        assert mathis["presence"] == {
            "home": True,
            "room": "salon",
            "since": arrived.isoformat().replace("+00:00", "Z"),
        }
        assert (await api.get("/api/v1/household/people/nobody")).json()["error"]["code"] == "person_unknown"


async def test_a_task_a_watch_a_satellite_and_an_account_open_one_by_one(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        nestor = admin.nestor
        member = await admin.account("mathilde", Role.MEMBER, "mathilde")
        theirs = await nestor.tasks.delegate("Plombier", origin=TELEGRAM, requested_by=MATHILDE)
        mine = await nestor.tasks.delegate("Dépôt", origin=TELEGRAM, requested_by=MATHIS)
        await asyncio.sleep(0.01)
        await nestor.tasks.cancel(mine.id)
        watch = await nestor.watch_book.create(Watch(what="le colis", owner=MATHIS))
        await pair_by_code(nestor.pairing, Manifest(Device("mic", "esp32", "bureau"), software=SOFTWARE))
        owner, guest = await admin.api(), await admin.api("mathilde")

        ended = (await owner.get(f"/api/v1/tasks/{mine.id}")).json()
        assert ended["status"] == "cancelled" and ended["ended_at"] is not None
        assert (await owner.get(f"/api/v1/tasks/{theirs.id}")).json()["ended_at"] is None
        assert (await guest.get(f"/api/v1/tasks/{theirs.id}")).status_code == 200
        assert (await guest.get(f"/api/v1/tasks/{mine.id}")).json()["error"]["code"] == "task_unknown"

        assert (await owner.get(f"/api/v1/watches/{watch.id}")).json()["what"] == "le colis"
        assert (await guest.get(f"/api/v1/watches/{watch.id}")).status_code == 404

        assert (await owner.get("/api/v1/satellites/mic")).json()["room"] == "bureau"
        assert (await owner.get("/api/v1/satellites/nope")).status_code == 404

        account = (await owner.get(f"/api/v1/accounts/{member.id}")).json()
        assert account["login"] == "mathilde" and account["last_seen_at"] is not None, "signed in just now"
        assert (await owner.get("/api/v1/accounts/nope")).status_code == 404
