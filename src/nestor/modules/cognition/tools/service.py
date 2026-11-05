"""The toolbox: every tool the agent may call, run safely and logged."""

import asyncio
import json
import time
from collections.abc import Iterable, Sequence

from nestor.core import ContractError
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools.events import ToolCalled, ToolCompleted
from nestor.modules.cognition.tools.ports import InWriting, ToolProvider
from nestor.modules.cognition.tools.types import Risk, Tool, ToolContext, ToolFailed, ToolOutput
from nestor.modules.identity import Identified
from nestor.modules.journal import Journal

CONFIRMED = {"type": "boolean", "description": "true only once the person explicitly agreed to this exact action"}


class Toolbox:
    """Fixed tools plus providers whose tools may change. A failing tool never breaks the
    conversation: the model receives the error and says so.

    It is also where who asked matters, the same for every tool:
    - a sensitive call is confirmed by the person who asks: in the conversation on their own account (the model
      calls again with `confirmed`), in writing on that account when asked aloud on a shared device or in a turn
      nobody takes part in (a wake-up);
    - a tool on someone's own data (`owner`) serves them only, and what it finds for a voice nobody recognised is
      written to them rather than said in the room.
    """

    def __init__(
        self,
        journal: Journal,
        tools: Iterable[Tool] = (),
        providers: Iterable[ToolProvider] = (),
        in_writing: InWriting | None = None,
    ) -> None:
        self._journal = journal
        self._fixed = tuple(tools)
        self._providers = tuple(providers)
        self.in_writing = in_writing  # set once built: it runs confirmed calls through this toolbox
        self._tools()  # fail early on duplicate names

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(_spec(tool) for tool in self._tools().values())

    async def call(self, call: ToolCall, context: ToolContext, *, confirmed: bool = False) -> str:
        """Run `call` for `context`; `confirmed`: the person agreed to it in writing already."""
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
        output, ok = await self._run(call, context, confirmed=confirmed)
        await self._journal.publish(
            ToolCompleted(
                source="toolbox",
                session=context.address.session,
                call_id=call.id,
                name=call.name,
                output=output,
                ok=ok,
                duration_s=round(time.monotonic() - started, 3),
                exchange=context.exchange,
            )
        )
        return output

    async def _run(self, call: ToolCall, context: ToolContext, *, confirmed: bool) -> tuple[str, bool]:
        tool = self._tools().get(call.name)
        if tool is None:
            return _error(f"unknown tool {call.name!r}"), False
        missing = [name for name in _required(tool) if name not in call.arguments]
        if missing:
            return _error(f"missing arguments: {', '.join(missing)}"), False
        arguments = {k: v for k, v in call.arguments.items() if k != "confirmed"}
        try:
            if tool.owner is not None and context.person != tool.owner:
                who = "ask who is asking first" if context.person is None else f"only {tool.owner} may use it"
                raise ToolFailed(f"this belongs to {tool.owner}: {who}")
            if tool.risk_of(arguments) is Risk.SENSITIVE and not confirmed:
                # in place only in a live conversation on their account: aloud on a satellite, or in a turn nobody
                # takes part in (a wake-up), the person confirms in writing
                if context.speaker.by is not Identified.ACCOUNT or context.exchange is None:
                    return _text(await self._confirm_in_writing(call, tool, context)), True
                if call.arguments.get("confirmed") is not True:
                    raise ToolFailed(
                        f"{tool.name} is sensitive: describe exactly what you will do, ask the person to confirm, "
                        "then call it again with confirmed=true"
                    )
            async with asyncio.timeout(tool.timeout_s):
                output = _text(await tool.run(arguments, context))
            if tool.owner is not None and not context.speaker.private and self.in_writing is not None:
                return _text(await self.in_writing.send(call, output, context)), True
        except TimeoutError:
            return _error(f"{tool.name} did not answer within {tool.timeout_s:g} s"), False
        except ToolFailed as failure:
            return _error(str(failure)), False
        except Exception as error:  # a broken tool must not break the conversation
            return _error(f"{tool.name} failed ({type(error).__name__})"), False
        return output, True

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


def _text(output: ToolOutput) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def _required(tool: Tool) -> Sequence[str]:
    required = tool.spec.parameters.get("required", ())
    return [str(name) for name in required] if isinstance(required, list | tuple) else []


def _error(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)
