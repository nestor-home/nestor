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
    TaskEnded,
)
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.conversation import Attached
from nestor.modules.identity import Speaker
from nestor.modules.journal import FileRef
from nestor.runtime import Nestor
from nestor.runtime.config import parse_config
from nestor.runtime.plugins import Family, Plugin
from nestor.testing.cognition import FakeRemote, ScriptedRemoteExecutor

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
        return next(
            r.assignment for r in self.remote.runs.values() if r.assignment.objective == self.objective(task_id)
        )

    def objective(self, task_id: str) -> str:
        return self.nestor.tasks.tasks[task_id].objective

    def reached(self, link: str) -> str:
        """A link as an executor follows it: here, on this machine, rather than at the public URL."""
        return self.served.url(link.removeprefix("https://nestor.example"))

    def finish(self, task_id: str) -> None:
        ref = self.nestor.tasks.tasks[task_id].ref
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
    registry.register(Plugin(Family.EXECUTOR, "reaching", NoSettings, reaching))
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
    task = await nestor.tasks.delegate(
        objective,
        title="Devis corrigé",
        origin=MAIN,
        requested_by=MATHIS,
        executor=executor,
        exchange=turn.exchange,
        given=(FileRef(quote, "devis.pdf"),),
    )
    await eventually(lambda: task.ref is not None)  # submitted: the executor holds its assignment
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
            "task_brief", "read_file", "recall", "remember", "report_progress",
            "ask_requester", "check_answer", "attach_file",
        }, "no home: no home_state"  # fmt: skip
        assert [f.name for f in given.files] == ["devis.pdf"] and "read_file gives a link" in given.brief()
        brief = await call(nestor, "task_brief", task=task)
        assert (brief["title"], brief["objective"]) == ("Devis corrigé", "Corrige le devis")
        assert (brief["requested_by"], brief["channel"]) == ("Mathis", "memory")
        assert any("Corrige le devis joint" in line for line in brief["conversation"])
        [file] = brief["files"]
        assert (file["name"], file["media_type"]) == ("devis.pdf", "application/pdf")
        read = await call(nestor, "read_file", task=task, file=file["file"])
        async with httpx.AsyncClient() as http:
            assert (await http.get(world.reached(read["url"]))).content == PDF, "no key: the link is enough"

        await world.nestor.memories.remember("Léa préfère les devis en PDF signés", about=PersonId("lea"), source=MAIN)
        await call(nestor, "remember", task=task, fact="Mathis préfère les devis en PDF")
        recalled = await call(nestor, "recall", task=task, query="devis PDF")
        texts = [m["text"] for m in recalled["memories"]]
        assert any("Mathis préfère les devis en PDF" in t for t in texts)
        assert not any("Léa" in t for t in texts), "only what is the requester's"

        await call(nestor, "report_progress", task=task, step="je relis les montants")
        assert "je relis les montants" in world.nestor.tasks.tasks[task_id].steps

        asked = await call(nestor, "ask_requester", task=task, question="La TVA est-elle à 20 % ?")
        assert (await call(nestor, "check_answer", task=task, question=asked["question"]))["status"] == "waiting"
        question = world.nestor.message_book.get(asked["question"])
        assert question is not None and (question.to, question.task) == (MATHIS, task_id)
        assert question.text == 'codex, working on "Devis corrigé": La TVA est-elle à 20 % ?', "the task by its name"
        await world.nestor.message_book.answer(asked["question"], "Oui, 20 %", by=MATHIS)
        answered = await call(nestor, "check_answer", task=task, question=asked["question"])
        assert answered == {"status": "answered", "answer": "Oui, 20 %"}

        corrected = b"%PDF-1.7 corrige" + bytes(5_000_000)  # bigger than an MCP request's usual cap
        upload = await call(nestor, "attach_file", task=task, name="devis-corrige.pdf", media_type="application/pdf")
        async with httpx.AsyncClient() as http:
            assert (await http.put(world.reached(upload["upload_url"]), content=corrected)).status_code == 200
            again = await http.put(world.reached(upload["upload_url"]), content=b"%PDF-1.7 autre")
            assert again.status_code == 404, "an upload link works once"

    world.finish(task_id)
    outcome = await world.nestor.tasks.wait(task_id)
    [ended] = [e for e in await world.nestor.journal.history(TaskEnded) if e.task_id == task_id]
    assert outcome.status.value == "completed" and len(ended.files) == 1
    assert ended.files[0].name == "devis-corrige.pdf", "by the name the executor gave it"
    assert await world.nestor.blobs.get(ended.files[0].blob.digest) == corrected
    calls = [c for c in await world.nestor.journal.history(ExecutorCalled) if c.task_id == task_id]
    assert {c.tool for c in calls} >= {"task_brief", "attach_file"} and all(
        c.ok and c.executor == "codex" for c in calls
    )


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
    assert len(set(refusals)) == 1 and "not a running task of yours" in refusals[0]
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
