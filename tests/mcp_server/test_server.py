"""Nestor's MCP server for executors, served over real HTTP and called by an MCP client: what an executor reaches for
its task with its key and the task's capability, the same refusal for anything else, and the task's files by
short-lived links."""

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette

from nestor.adapters.tools.mcp.provider import BearerToken, McpToolProvider
from nestor.core import PersonId
from nestor.mcp_server import ExecutorServer, guard
from nestor.modules.channels import Address, AttachmentKind, Medium
from nestor.modules.cognition.delegation import (
    Assignment,
    ExecutorCalled,
    NestorTools,
    Outcome,
    TurnEnded,
)
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.conversation import Attached
from nestor.modules.identity import Speaker
from nestor.modules.journal import FileRef
from nestor.modules.memory import Place
from nestor.runtime import Nestor
from nestor.runtime.config import parse_config
from nestor.runtime.plugins import Family, Plugin
from nestor.testing.cognition import FakeRemote, ScriptedRemoteExecutor
from nestor.testing.system import DOUBLE

from ..adapters.served import Served, eventually
from ..runtime.fakes import Fakes, NoSettings

MAIN = Address("memory", "main")
MATHIS = PersonId("mathis")
PDF = b"%PDF-1.7 devis"
CONFIG = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie., timezone: Europe/Paris}}
household:
  - {{id: mathis, name: Mathis, accounts: ["memory:user"], reach: "memory:main"}}
  - {{id: lea, name: Léa}}
models: {{main: {{type: language, provider: scripted, replies: []}}}}
executors: [{{kind: reaching, name: codex}}, {{kind: reaching, name: claude}}]
channels: [{{kind: memory}}]
admin: {{public_url: "https://nestor.example"}}
"""


class Reaching(ScriptedRemoteExecutor):
    """Remote work that reaches Nestor's MCP server with what Nestor passes it, and runs until finished."""

    nestor_tools = NestorTools.PASSED


@dataclass
class World:
    nestor: Nestor
    served: Served
    remote: FakeRemote

    def given(self, task_id: str) -> Assignment:
        """What the working turn of the task was given."""
        ref = self.nestor.tasks.tasks[task_id].turn.ref
        return self.remote.runs[str(ref)].assignment

    def reached(self, link: str) -> str:
        """A link as an executor follows it: here, on this machine, rather than at the public URL."""
        return self.served.url(link.removeprefix("https://nestor.example"))

    def finish(self, task_id: str) -> None:
        ref = self.nestor.tasks.tasks[task_id].turn.ref
        assert ref is not None
        self.remote.finish(ref, Outcome.completed("ok"))


@pytest.fixture
async def world(tmp_path: Path) -> AsyncIterator[World]:
    fakes, remote = Fakes(), FakeRemote()

    def reaching(settings: NoSettings, name: str, services: Any) -> Reaching:
        executor = Reaching(remote, duration_s=None)
        executor.name = name
        return executor

    registry = fakes.registry()
    registry.register(Plugin(Family.EXECUTOR, "reaching", NoSettings, reaching, card=DOUBLE))
    environ = {"NESTOR_SECRET_KEY": "k" * 43}
    nestor = Nestor(parse_config(CONFIG.format(data_dir=tmp_path), environ), registry, environ=environ)
    async with nestor:
        assert nestor.executor_keys is not None
        server = ExecutorServer(nestor, nestor.executor_keys)

        @asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncGenerator[None]:
            async with server.running():
                yield

        served = Served(lambda: Starlette(routes=server.routes("/mcp"), lifespan=lifespan))
        await served.start()
        try:
            yield World(nestor, served, remote)
        finally:
            await served.stop()


async def delegated(world: World, objective: str, executor: str = "codex") -> tuple[str, Assignment]:
    """A task Mathis handed over in writing, right after sending a quote."""
    nestor = world.nestor
    turn = await nestor.agent.conversations.turn(MAIN, Medium.WRITTEN)
    quote = await nestor.blobs.put(PDF, "application/pdf")
    sent = (Attached(kind=AttachmentKind.FILE, blob=quote, name="devis.pdf"),)
    await turn.said("Corrige le devis joint", Medium.WRITTEN, Speaker.account(MATHIS), sent)
    task = await nestor.tasks.start_task(
        objective,
        title="Devis corrigé",
        origin=MAIN,
        owner=MATHIS,
        executor=executor,
        exchange=turn.exchange,
        given=(FileRef(quote, "devis.pdf"),),
    )
    await eventually(lambda: task.turn.ref is not None)  # submitted: the executor holds its assignment
    return task.id, world.given(task.id)


@asynccontextmanager
async def client(world: World, key: str) -> AsyncGenerator[McpToolProvider]:
    async with McpToolProvider(world.served.url(), name="nestor", auth=BearerToken(key), timeout_s=5.0) as provider:
        yield provider


async def call(provider: McpToolProvider, tool_name: str, /, **arguments: object) -> dict[str, Any]:
    tool = next(t for t in provider.tools() if t.name == tool_name)
    output = await tool.run(arguments, ToolContext(address=MAIN))
    assert isinstance(output, str)
    return json.loads(output)


async def test_an_executor_works_on_its_task_through_nestor_s_tools(world: World) -> None:
    task_id, given = await delegated(world, "Corrige le devis")
    assert given.access is not None and given.task is not None
    assert given.access.url == "https://nestor.example/mcp"
    task = given.task
    async with client(world, given.access.key) as nestor:
        assert {t.name for t in nestor.tools()} == {
            "task_brief", "read_file", "recall", "note", "report_progress", "attach_file",
        }, "no home: no home_state"  # fmt: skip
        assert [f.name for f in given.files] == ["devis.pdf"] and "read_file gives a link" in given.brief()
        brief = await call(nestor, "task_brief", task=task)
        assert (brief["title"], brief["instruction"]) == ("Devis corrigé", "Corrige le devis")
        assert (brief["for"], brief["channel"], brief["earlier_turns"]) == ("Mathis", "memory", [])
        assert any("Corrige le devis joint" in line for line in brief["conversation"])
        [file] = brief["files"]
        assert (file["name"], file["media_type"]) == ("devis.pdf", "application/pdf")
        read = await call(nestor, "read_file", task=task, file=file["file"])
        async with httpx.AsyncClient() as http:
            assert (await http.get(world.reached(read["url"]))).content == PDF, "no key: the link is enough"

        await world.nestor.memories.remember(
            "Léa préfère les devis en PDF signés", place=Place.of(PersonId("lea")), source=MAIN
        )
        await world.nestor.memories.remember("Mathis préfère les devis en PDF", place=Place.of(MATHIS), source=MAIN)
        await call(nestor, "note", task=task, text="Le devis est en TVA à 20 %.")
        recalled = await call(nestor, "recall", task=task, query="devis PDF TVA")
        texts = [m["text"] for m in recalled["memories"]]
        assert any("Mathis préfère les devis en PDF" in t for t in texts)
        assert not any("Léa" in t for t in texts), "only what is the owner's"
        assert not any("TVA" in t for t in texts), "a note stays with the task, never in anyone's memory"
        assert (await call(nestor, "task_brief", task=task))["notes"] == ["Le devis est en TVA à 20 %."]

        await call(nestor, "report_progress", task=task, step="je relis\n  les montants " + "0" * 300)
        said = world.nestor.tasks.tasks[task_id].turn.steps[-1]
        assert said.startswith("je relis les montants 00") and len(said) < 200, "one short line, as the executor's own"

        corrected = b"%PDF-1.7 corrige" + bytes(5_000_000)  # bigger than an MCP request's usual cap
        upload = await call(nestor, "attach_file", task=task, name="devis-corrige.pdf", media_type="application/pdf")
        async with httpx.AsyncClient() as http:
            assert (await http.put(world.reached(upload["upload_url"]), content=corrected)).status_code == 200
            again = await http.put(world.reached(upload["upload_url"]), content=b"%PDF-1.7 autre")
            assert again.status_code == 404, "an upload link works once"

    world.finish(task_id)
    outcome = await world.nestor.tasks.wait(task_id)
    [ended] = [e for e in await world.nestor.journal.history(TurnEnded) if e.task_id == task_id]
    assert outcome.status.value == "completed" and len(ended.files) == 1
    assert ended.files[0].name == "devis-corrige.pdf", "by the name the executor gave it"
    assert await world.nestor.blobs.get(ended.files[0].blob.digest) == corrected
    calls = [c for c in await world.nestor.journal.history(ExecutorCalled) if c.task_id == task_id]
    assert {c.tool for c in calls} >= {"task_brief", "attach_file"} and all(
        c.ok and c.executor == "codex" for c in calls
    )

    await world.nestor.tasks.direct(task_id, "Ajoute la remise de 5 %", by=MATHIS)
    await eventually(lambda: world.nestor.tasks.tasks[task_id].turn.ref is not None)
    next_turn = world.given(task_id)
    assert next_turn.task and next_turn.task != task and next_turn.access is not None
    async with client(world, next_turn.access.key) as nestor:
        brief = await call(nestor, "task_brief", task=next_turn.task)
    assert brief["instruction"] == "Ajoute la remise de 5 %"
    assert [t["asked"] for t in brief["earlier_turns"]] == ["Corrige le devis"], "the turns before, in the brief"
    world.finish(task_id)


async def test_another_executor_s_task_an_ended_task_or_a_guess_all_read_the_same(world: World) -> None:
    codex_task, given = await delegated(world, "Corrige le devis")
    _, claude = await delegated(world, "Relis le contrat", executor="claude")
    assert given.task and claude.access
    async with client(world, claude.access.key) as nestor:
        refusals = []
        for task in (given.task, "nstt_guessed"):
            with pytest.raises(ToolFailed) as refused:
                await call(nestor, "task_brief", task=task)
            refusals.append(str(refused.value))
    assert given.access is not None
    async with client(world, given.access.key) as nestor:
        [file] = (await call(nestor, "task_brief", task=given.task))["files"]
        link = (await call(nestor, "read_file", task=given.task, file=file["file"]))["url"]
    world.finish(codex_task)
    await world.nestor.tasks.wait(codex_task)
    async with httpx.AsyncClient() as http:
        assert (await http.get(world.reached(link))).status_code == 404, "a link ends with its task"
        forged = link[:-3] + ("abc" if not link.endswith("abc") else "xyz")
        assert (await http.get(world.reached(forged))).status_code == 404
    async with client(world, given.access.key) as nestor:
        with pytest.raises(ToolFailed) as ended:
            await call(nestor, "task_brief", task=given.task)
        refusals.append(str(ended.value))
    assert len(set(refusals)) == 1 and "not a working turn of yours" in refusals[0]
    refused_calls = [c for c in await world.nestor.journal.history(ExecutorCalled) if not c.ok]
    assert len(refused_calls) == 3 and all(c.task_id is None for c in refused_calls)


@pytest.mark.parametrize("key", ["", "nstx_wrong", "revoked"])
async def test_a_request_without_a_known_key_is_refused_before_any_tool(world: World, key: str) -> None:
    _, given = await delegated(world, "Corrige le devis")
    assert given.access is not None
    if key == "revoked":
        key = given.access.key
        assert world.nestor.executor_keys is not None
        await world.nestor.executor_keys.revoke("codex")
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    headers = {"Accept": "application/json, text/event-stream"} | ({"Authorization": f"Bearer {key}"} if key else {})
    async with httpx.AsyncClient() as http:
        answer = await http.post(world.served.url(), json=initialize, headers=headers)
    assert answer.status_code == 401 and answer.text == "unauthorized"
    assert answer.headers["www-authenticate"].startswith("Bearer"), "the scheme it expects"


async def test_a_key_calling_too_often_is_held_back(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _, given = await delegated(world, "Corrige le devis")
    assert given.access is not None
    monkeypatch.setattr(guard, "CALLS_PER_MINUTE", 3)
    headers = {"Authorization": f"Bearer {given.access.key}", "Accept": "application/json, text/event-stream"}
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    async with httpx.AsyncClient() as http:
        statuses = [
            (await http.post(world.served.url(), json=initialize, headers=headers)).status_code for _ in range(4)
        ]
    assert statuses[-1] == 429 and 429 not in statuses[:3]


async def test_it_answers_at_the_admin_s_public_address_not_only_on_this_machine(world: World) -> None:
    _, given = await delegated(world, "Corrige le devis")
    assert given.access is not None
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    }
    headers = {
        "Authorization": f"Bearer {given.access.key}",
        "Accept": "application/json, text/event-stream",
        "Host": "nestor.example",  # as through the public URL, a VPN or Tailscale
    }
    async with httpx.AsyncClient() as http:
        answer = await http.post(world.served.url(), json=initialize, headers=headers)
    assert answer.status_code == 200, answer.text


async def test_a_turn_given_in_another_conversation_is_briefed_from_that_one(world: World) -> None:
    task_id, _ = await delegated(world, "Corrige le devis")
    world.finish(task_id)
    await world.nestor.tasks.wait(task_id)
    elsewhere = Address("memory", "kitchen")
    turn = await world.nestor.agent.conversations.turn(elsewhere, Medium.WRITTEN)
    await turn.said("Ajoute la remise de 5 % au devis", Medium.WRITTEN, Speaker.account(MATHIS))
    await world.nestor.tasks.direct(
        task_id, "Ajoute la remise de 5 %", by=MATHIS, origin=elsewhere, exchange=turn.exchange
    )
    await eventually(lambda: world.nestor.tasks.tasks[task_id].turn.ref is not None)
    given = world.given(task_id)
    assert given.access is not None and given.task is not None
    async with client(world, given.access.key) as nestor:
        brief = await call(nestor, "task_brief", task=given.task)
    assert any("Ajoute la remise de 5 % au devis" in line for line in brief["conversation"])
    assert not any("Corrige le devis joint" in line for line in brief["conversation"]), "not the task's first one"
    world.finish(task_id)


async def test_a_link_ends_with_its_turn_even_while_the_task_goes_on(world: World) -> None:
    task_id, given = await delegated(world, "Corrige le devis")
    assert given.access is not None and given.task is not None
    async with client(world, given.access.key) as nestor:
        [file] = (await call(nestor, "task_brief", task=given.task))["files"]
        download = (await call(nestor, "read_file", task=given.task, file=file["file"]))["url"]
        upload = await call(nestor, "attach_file", task=given.task, name="tard.pdf", media_type="application/pdf")
    world.finish(task_id)
    await world.nestor.tasks.wait(task_id)
    await world.nestor.tasks.direct(task_id, "Ajoute la remise de 5 %", by=MATHIS)
    await eventually(lambda: world.nestor.tasks.tasks[task_id].turn.ref is not None)
    async with httpx.AsyncClient() as http:
        assert (await http.put(world.reached(upload["upload_url"]), content=b"%PDF-1.7 tard")).status_code == 404
        assert (await http.get(world.reached(download))).status_code == 404
    assert world.nestor.tasks.tasks[task_id].turn.files == [], "a late file never lands on the next turn"
    world.finish(task_id)
