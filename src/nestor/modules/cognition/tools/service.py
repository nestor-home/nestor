"""The toolbox: every tool the agent may call, run safely and logged."""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nestor.core import Component, ContractError
from nestor.modules.channels import Attachment
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools.events import ToolCalled, ToolCompleted, ToolDeferred, ToolReturned
from nestor.modules.cognition.tools.ports import InWriting, ToolProvider
from nestor.modules.cognition.tools.results import Results
from nestor.modules.cognition.tools.types import Made, Risk, Tool, ToolContext, ToolFailed, ToolOutput
from nestor.modules.identity import Identified
from nestor.modules.journal import BlobStore, FileRef, Journal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Called:
    """What a call gave the turn: `output` for the model, whether it worked, the files it made and the pictures it
    gave the model to look at, kept."""

    output: str
    ok: bool = True
    files: tuple[FileRef, ...] = ()
    seen: tuple[FileRef, ...] = ()


class Toolbox(Component):
    """Fixed tools plus providers whose tools may change. A failing tool never breaks the
    conversation: the model receives the error and says so.

    A turn waits for a call a while at most (`wait_s`): past that, the call goes on in the background, the model is told
    its result will come back, and the turn ends; the agent stays available. The result comes back as `ToolReturned`,
    which the conversation receives as a notification. A result too long for a turn goes to `results`; the files a
    tool makes (`Made`) go to `blobs`, and with the answer.

    It is also where who asked matters, the same for every tool:
    - a sensitive call waits for the person who asks to confirm it (`InWriting.confirm`): in the conversation when it
      is on their own account, in writing on that account when asked aloud on a shared device or in a turn nobody
      takes part in (an alert); a tool whose call their account is enough for (`account_vouches`) runs at once in
      such a conversation. The model never confirms anything itself: it asks, and the person answers;
    - a tool on someone's own data (`owner`) serves them only, and what it finds for a voice nobody recognised is
      written to them rather than said in the room.
    """

    name = "toolbox"

    def __init__(
        self,
        journal: Journal,
        tools: Iterable[Tool] = (),
        providers: Iterable[ToolProvider] = (),
        in_writing: InWriting | None = None,
        results: Results | None = None,
        blobs: BlobStore | None = None,
    ) -> None:
        self._journal, self._blobs = journal, blobs
        self._fixed = tuple(tools)
        self._providers = (*providers, *((results,) if results else ()))
        self.in_writing = in_writing  # set once built: it runs confirmed calls through this toolbox
        self._results = results
        self._late: set[asyncio.Task[None]] = set()  # deferred calls still running
        self._tools()  # fail early on duplicate names

    async def close(self) -> None:
        """Stop the deferred calls: their results never come back (`Returns` tells so after a restart)."""
        for task in tuple(self._late):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(_spec(tool) for tool in self._tools().values())

    async def call(
        self, call: ToolCall, context: ToolContext, *, confirmed: bool = False, wait_s: float | None = None
    ) -> Called:
        """Run `call` for `context`; `confirmed`: the person already approved it (`InWriting.confirm`). `wait_s`: how
        long the turn waits for it before it goes on in the background; `None`, until it ends. Files it made come with
        it, or with its result when it went on in the background."""
        tool = self._tools().get(call.name)
        await self._journal.publish(
            ToolCalled(
                source="toolbox",
                session=context.address.session,
                address=context.address,
                call_id=call.id,
                name=call.name,
                arguments=dict(call.arguments),
                person=context.person,
                exchange=context.exchange,
                connection_id=tool.connection if tool else None,
            )
        )
        started = time.monotonic()
        running = asyncio.create_task(self._result(call, tool, context, confirmed=confirmed), name=f"tool {call.name}")
        try:
            await asyncio.wait({running}, timeout=wait_s)
        except asyncio.CancelledError:  # the turn was cut: so is what it waited for
            running.cancel()
            raise
        if not running.done():
            return Called(await self._defer(call, context, running, started))
        called = running.result()
        await self._journal.publish(
            ToolCompleted(
                source="toolbox",
                session=context.address.session,
                call_id=call.id,
                name=call.name,
                output=called.output,
                ok=called.ok,
                duration_s=_since(started),
                files=called.files,
                seen=called.seen,
                exchange=context.exchange,
            )
        )
        return called

    async def _defer(self, call: ToolCall, context: ToolContext, running: asyncio.Task[Called], started: float) -> str:
        output = json.dumps(
            {
                "pending": f"{call.name} is still running. Its result will come back in this conversation by itself: "
                "say so if it matters, do not wait for it or call it again."
            }
        )
        await self._journal.publish(
            ToolDeferred(
                source="toolbox",
                session=context.address.session,
                address=context.address,
                call_id=call.id,
                name=call.name,
                arguments=dict(call.arguments),
                output=output,
                person=context.person,
                exchange=context.exchange,
                thread=context.thread,
                asked=context.asked,
            )
        )

        async def returned() -> None:
            called = await running
            await self._journal.publish(
                ToolReturned(
                    source="toolbox",
                    session=context.address.session,
                    call_id=call.id,
                    name=call.name,
                    output=called.output,
                    ok=called.ok,
                    duration_s=_since(started),
                    files=called.files,
                    seen=called.seen,
                    exchange=context.exchange,
                )
            )

        late = asyncio.create_task(returned(), name=f"tool {call.name} returning")
        self._late.add(late)
        late.add_done_callback(self._late.discard)
        return output

    async def _result(self, call: ToolCall, tool: Tool | None, context: ToolContext, *, confirmed: bool) -> Called:
        try:
            ran = await self._run(call, tool, context, confirmed=confirmed)
        except ToolFailed as failure:
            return Called(_error(str(failure)), ok=False)
        except Exception as error:  # a broken tool must not break the conversation
            return Called(_error(f"{call.name} failed ({type(error).__name__})"), ok=False)
        output = _text(ran.output)
        if self._results is not None:
            output = await self._results.fit(call, output, context)
        blobs = self._blobs
        if blobs is None:
            if ran.files or ran.seen:
                logger.warning("%s gave files, but there is nowhere to keep them: they are left out", call.name)
            return Called(output)
        return Called(output, files=await _kept(blobs, ran.files), seen=await _kept(blobs, ran.seen))

    async def _run(self, call: ToolCall, tool: Tool | None, context: ToolContext, *, confirmed: bool) -> Made:
        """What the tool gave: for the model, files and pictures; `ToolFailed` says why it did not run, any other error
        that the tool broke."""
        if tool is None:
            raise ToolFailed(f"unknown tool {call.name!r}")
        missing = [name for name in _required(tool) if name not in call.arguments]
        if missing:
            raise ToolFailed(f"missing arguments: {', '.join(missing)}")
        arguments = call.arguments
        if tool.owner is not None and context.person != tool.owner:
            who = "ask who is asking first" if context.person is None else f"only {tool.owner} may use it"
            raise ToolFailed(f"this belongs to {tool.owner}: {who}")
        if tool.vouched and (context.speaker.by is not Identified.ACCOUNT or context.person is None):
            raise ToolFailed(f"{tool.name} needs to know for sure who asks: they ask from their own account")
        if tool.risk_of(arguments) is Risk.SENSITIVE and not confirmed and not (tool.account_vouches and context.live):
            return Made(await self._confirm(call, tool, context))
        try:
            async with asyncio.timeout(tool.timeout_s):
                ran = await tool.run(arguments, context)
        except TimeoutError:
            raise ToolFailed(f"{tool.name} did not answer within {tool.timeout_s:g} s") from None
        made = ran if isinstance(ran, Made) else Made(ran)
        if tool.owner is not None and not context.speaker.private and self.in_writing is not None:
            return Made(await self.in_writing.send(call, _text(made.output), context))
        return made

    async def _confirm(self, call: ToolCall, tool: Tool, context: ToolContext) -> ToolOutput:
        if context.person is None:
            raise ToolFailed("this is sensitive: ask who is asking, then they confirm it on their account")
        if self.in_writing is None:
            raise ToolFailed("this is sensitive and cannot be confirmed from here: it needs the person's own account")
        return await self.in_writing.confirm(call, context, about=tool.spec.description)

    def _tools(self) -> dict[str, Tool]:
        found: dict[str, Tool] = {}
        for tool in (*self._fixed, *(t for p in self._providers for t in p.tools())):
            if tool.name in found:
                raise ContractError(f"two tools are named {tool.name!r}")
            found[tool.name] = tool
        return found


def _spec(tool: Tool) -> ToolSpec:
    """What the model sees of a tool: one that may need confirming says so."""
    if not tool.may_need_confirming:
        return tool.spec
    description = f"{tool.spec.description} Sensitive: the person confirms first."
    return ToolSpec(tool.spec.name, description, tool.spec.parameters)


async def _kept(blobs: BlobStore, files: tuple[Attachment, ...]) -> tuple[FileRef, ...]:
    return tuple([FileRef(await blobs.put(f.data, f.media_type), f.file_name) for f in files])


def _since(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _text(output: ToolOutput) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def _required(tool: Tool) -> Sequence[str]:
    required = tool.spec.parameters.get("required", ())
    return [str(name) for name in required] if isinstance(required, list | tuple) else []


def _error(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)
