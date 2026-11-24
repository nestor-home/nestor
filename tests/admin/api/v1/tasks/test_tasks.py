"""Tasks in the admin: listed by how they stand, opened as their thread, directed (an answer to their question, a new
instruction, steering while they work), stopped, renamed, archived, and their files downloaded, each by whoever
reaches them only."""

import asyncio
from pathlib import Path

from nestor.core import PersonId
from nestor.modules.accounts import Role
from nestor.modules.channels import Address, Attachment, AttachmentKind
from nestor.modules.cognition import Outcome, TaskState
from nestor.modules.cognition.delegation import Task, TurnEnded

from ....harness import Harness

TELEGRAM = Address("telegram", "42")
MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


async def handed(admin: Harness, title: str, owner: PersonId = MATHIS) -> Task:
    """A task working remotely, its turn submitted."""
    before = len(admin.remote.runs)
    task = await admin.nestor.tasks.start_task(title, title=title, origin=TELEGRAM, owner=owner)
    while len(admin.remote.runs) == before or task.turn.ref is None:
        await asyncio.sleep(0.01)
    return task


async def ended(admin: Harness, count: int) -> None:
    while len(await admin.nestor.journal.history(TurnEnded)) < count:
        await asyncio.sleep(0.01)


async def test_tasks_are_listed_waiting_first_and_reach_only_their_owner_or_who_manages_all(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        working = await handed(admin, "Site")
        asking = await handed(admin, "Lave-vaisselle")
        admin.remote.finish(str(asking.turn.ref), Outcome.asked("Quelle marque ?"))
        hers = await handed(admin, "Plombier", owner=MATHILDE)
        await ended(admin, 1)
        owner, member = await admin.api(), await admin.api("mathilde")

        listed = (await owner.get("/api/v1/tasks")).json()["tasks"]
        assert [(t["title"], t["state"]) for t in listed][:2] == [
            ("Lave-vaisselle", "waiting"),
            ("Plombier", "working"),
        ]
        assert listed[0]["question"] == "Quelle marque ?" and {t["id"] for t in listed} == {
            working.id,
            asking.id,
            hers.id,
        }
        assert [t["id"] for t in (await member.get("/api/v1/tasks")).json()["tasks"]] == [hers.id], "hers only"
        assert (await member.get(f"/api/v1/tasks/{working.id}")).json()["error"]["code"] == "task_unknown"
        for path in ("instructions", "stop", "archive"):
            refused = await member.post(f"/api/v1/tasks/{working.id}/{path}", {"text": "x"})
            assert refused.status_code == 404, path
        assert (await member.patch(f"/api/v1/tasks/{working.id}", {"title": "Autre"})).status_code == 404
        for task in (working, hers):
            await admin.nestor.tasks.stop(task.id)


async def test_answering_a_question_opens_the_next_turn_of_the_same_thread(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        task = await handed(admin, "Lave-vaisselle")
        admin.remote.finish(str(task.turn.ref), Outcome.asked("Quelle marque ?", session="thread-1"))
        await ended(admin, 1)
        api = await admin.api()

        directed = (await api.post(f"/api/v1/tasks/{task.id}/instructions", {"text": "Hisense"})).json()
        assert directed["steered"] is False
        thread = directed["task"]["thread"]
        assert [(t["instruction"], t["status"]) for t in thread] == [
            ("Lave-vaisselle", "asked"),
            ("Hisense", "running"),
        ]
        assert thread[0]["question"] == "Quelle marque ?" and thread[1]["by"]["id"] == "mathis"
        while task.turn.ref is None:
            await asyncio.sleep(0.01)
        assert admin.remote.runs[task.turn.ref].assignment.session == "thread-1", "in the session that asked"
        await admin.nestor.tasks.stop(task.id)


async def test_an_instruction_while_it_works_steers_it_and_a_stop_leaves_the_task(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        task = await handed(admin, "Site")
        api = await admin.api()
        directed = (await api.post(f"/api/v1/tasks/{task.id}/instructions", {"text": "Et la page contact"})).json()
        assert directed["steered"] is True and len(directed["task"]["thread"]) == 1
        assert admin.remote.runs[str(task.turn.ref)].steered == ["Et la page contact"]

        stopped = (await api.post(f"/api/v1/tasks/{task.id}/stop")).json()
        assert stopped["confirmed"] is True and stopped["task"]["state"] == "ready"
        renamed = (await api.patch(f"/api/v1/tasks/{task.id}", {"title": "Site de la famille"})).json()
        assert renamed["title"] == "Site de la famille"
        archived = (await api.post(f"/api/v1/tasks/{task.id}/archive")).json()
        assert archived["state"] == "archived"
        assert (await api.get("/api/v1/tasks")).json()["tasks"] == [], "put away"
        assert [t["id"] for t in (await api.get("/api/v1/tasks", archived="true")).json()["tasks"]] == [task.id]
        assert task.state is TaskState.ARCHIVED


async def test_an_account_with_no_person_cannot_give_an_instruction(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        task = await handed(admin, "Site")
        await admin.account("gardien", Role.ADMIN)
        refused = await (await admin.api("gardien")).post(f"/api/v1/tasks/{task.id}/instructions", {"text": "x"})
        assert refused.json()["error"]["code"] == "person_required"
        await admin.nestor.tasks.stop(task.id)


async def test_the_files_of_a_turn_download_for_who_reaches_the_task(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        task = await handed(admin, "Le devis en PDF")
        made = Attachment(
            kind=AttachmentKind.FILE, data=b"%PDF-1.7 devis", media_type="application/pdf", name="devis.pdf"
        )
        admin.remote.finish(str(task.turn.ref), Outcome.completed("Le devis est prêt.", files=(made,)))
        await ended(admin, 1)
        owner, guest = await admin.api(), await admin.api("mathilde")
        turn = task.turn.id

        [listed] = (await owner.get(f"/api/v1/tasks/{task.id}")).json()["thread"]
        assert listed["files"] == [
            {
                "index": 0,
                "name": "devis.pdf",
                "kind": "file",
                "media_type": "application/pdf",
                "size": 14,
                "given": False,
            }
        ]
        got = await owner.get(f"/api/v1/tasks/{task.id}/turns/{turn}/files/0")
        assert (got.status_code, got.content, got.headers["content-type"]) == (
            200,
            b"%PDF-1.7 devis",
            "application/octet-stream",
        ), "downloaded, never shown in place"
        assert "devis.pdf" in got.headers["content-disposition"], "by the name the executor gave it"
        assert (await owner.get(f"/api/v1/tasks/{task.id}/turns/{turn}/files/1")).status_code == 404
        assert (await owner.get(f"/api/v1/tasks/{task.id}/turns/nope/files/0")).status_code == 404
        assert (await guest.get(f"/api/v1/tasks/{task.id}/turns/{turn}/files/0")).json()["error"][
            "code"
        ] == "task_unknown"
