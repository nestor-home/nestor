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
from nestor.modules.journal import BlobRef, BlobStore, Journal

logger = logging.getLogger(__name__)

CONFIRMED = {"type": "boolean", "description": "true only once the person explicitly agreed to this exact action"}


@dataclass(frozen=True, slots=True)
class Called:
    """What a call gave the turn: `output` for the model, whether it worked, and the files it made, kept."""

    output: str
    ok: bool = True
    files: tuple[BlobRef, ...] = ()


class Toolbox(Component):
    """Fixed tools plus providers whose tools may change. A failing tool never breaks the
    conversation: the model receives the error and says so.

    A turn waits for a call a while at most (`wait_s`): past that, the call goes on in the background, the model is told
    its result will come back, and the turn ends; the agent stays available. The result comes back as `ToolReturned`,
    which the conversation receives as a notification. A result too long for a turn goes to `results`; the files a
    tool makes (`Made`) go to `blobs`, and with the answer.

    It is also where who asked matters, the same for every tool:
    - a sensitive call is confirmed by the person who asks: in the conversation on their own account (the model
      calls again with `confirmed`), in writing on that account when asked aloud on a shared device or in a turn
      nobody takes part in (a wake-up);
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
        """Run `call` for `context`; `confirmed`: the person agreed to it in writing already. `wait_s`: how long the
        turn waits for it before it goes on in the background; `None`, until it ends. Files it made come with it,
        or with its result when it went on in the background."""
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
            )
        )
        started = time.monotonic()
        running = asyncio.create_task(self._result(call, context, confirmed=confirmed), name=f"tool {call.name}")
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
                    exchange=context.exchange,
                )
            )

        late = asyncio.create_task(returned(), name=f"tool {call.name} returning")
        self._late.add(late)
        late.add_done_callback(self._late.discard)
        return output

    async def _result(self, call: ToolCall, context: ToolContext, *, confirmed: bool) -> Called:
        try:
            output, made = await self._run(call, context, confirmed=confirmed)
        except ToolFailed as failure:
            return Called(_error(str(failure)), ok=False)
        except Exception as error:  # a broken tool must not break the conversation
            return Called(_error(f"{call.name} failed ({type(error).__name__})"), ok=False)
        if self._results is not None:
            output = await self._results.fit(call, output, context)
        blobs = self._blobs
        if blobs is None:
            if made:
                logger.warning("%s made files, but there is nowhere to keep them: they are left out", call.name)
            return Called(output)
        return Called(output, files=tuple([await blobs.put(f.data, f.media_type) for f in made]))

    async def _run(
        self, call: ToolCall, context: ToolContext, *, confirmed: bool
    ) -> tuple[str, tuple[Attachment, ...]]:
        """What the model receives and the files the tool made; `ToolFailed` says why it did not run, any other error
        that the tool broke."""
        tool = self._tools().get(call.name)
        if tool is None:
            raise ToolFailed(f"unknown tool {call.name!r}")
        missing = [name for name in _required(tool) if name not in call.arguments]
        if missing:
            raise ToolFailed(f"missing arguments: {', '.join(missing)}")
        arguments = {k: v for k, v in call.arguments.items() if k != "confirmed"}
        if tool.owner is not None and context.person != tool.owner:
            who = "ask who is asking first" if context.person is None else f"only {tool.owner} may use it"
            raise ToolFailed(f"this belongs to {tool.owner}: {who}")
        if tool.risk_of(arguments) is Risk.SENSITIVE and not confirmed:
            # in place only in a live conversation on their account: aloud on a satellite, or in a turn nobody
            # takes part in (a wake-up), the person confirms in writing
            if context.speaker.by is not Identified.ACCOUNT or context.exchange is None:
                return _text(await self._confirm_in_writing(call, tool, context)), ()
            if call.arguments.get("confirmed") is not True:
                raise ToolFailed(
                    f"{tool.name} is sensitive: describe exactly what you will do, ask the person to confirm, "
                    "then call it again with confirmed=true"
                )
        try:
            async with asyncio.timeout(tool.timeout_s):
                ran = await tool.run(arguments, context)
        except TimeoutError:
            raise ToolFailed(f"{tool.name} did not answer within {tool.timeout_s:g} s") from None
        output, made = (_text(ran.output), ran.files) if isinstance(ran, Made) else (_text(ran), ())
        if tool.owner is not None and not context.speaker.private and self.in_writing is not None:
            return _text(await self.in_writing.send(call, output, context)), ()
        return output, made

    async def _confirm_in_writing(self, call: ToolCall, tool: Tool, context: ToolContext) -> ToolOutput:
        if context.person is None:
            raise ToolFailed("this is sensitive: ask who is asking, then they confirm it in writing")
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
    """What the model sees of a tool: one that may need confirming takes `confirmed`."""
    if not tool.may_need_confirming:
        return tool.spec
    parameters = dict(tool.spec.parameters)
    existing = parameters.get("properties")
    parameters["properties"] = {**(existing if isinstance(existing, dict) else {}), "confirmed": CONFIRMED}
    description = f"{tool.spec.description} Sensitive: the person confirms first."
    return ToolSpec(tool.spec.name, description, parameters)


def _since(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _text(output: ToolOutput) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def _required(tool: Tool) -> Sequence[str]:
    required = tool.spec.parameters.get("required", ())
    return [str(name) for name in required] if isinstance(required, list | tuple) else []


def _error(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)
