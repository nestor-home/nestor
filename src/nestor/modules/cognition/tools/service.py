"""The toolbox: every tool the agent may call, run safely and logged."""

import asyncio
import json
import time
from collections.abc import Iterable, Sequence

from nestor.core import ContractError
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools.events import ToolCalled, ToolCompleted
from nestor.modules.cognition.tools.ports import ToolProvider
from nestor.modules.cognition.tools.types import Tool, ToolContext, ToolFailed
from nestor.modules.journal import Journal


class Toolbox:
    """Fixed tools plus providers whose tools may change. A failing tool never breaks the
    conversation: the model receives the error and says so."""

    def __init__(self, journal: Journal, tools: Iterable[Tool] = (), providers: Iterable[ToolProvider] = ()) -> None:
        self._journal = journal
        self._fixed = tuple(tools)
        self._providers = tuple(providers)
        self._tools()  # fail early on duplicate names

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec for tool in self._tools().values())

    async def call(self, call: ToolCall, context: ToolContext) -> str:
        await self._journal.publish(
            ToolCalled(
                source="toolbox",
                session=context.address.session,
                address=context.address,
                call_id=call.id,
                name=call.name,
                arguments=dict(call.arguments),
                person=context.person,
            )
        )
        started = time.monotonic()
        output, ok = await self._run(call, context)
        await self._journal.publish(
            ToolCompleted(
                source="toolbox",
                session=context.address.session,
                call_id=call.id,
                name=call.name,
                output=output,
                ok=ok,
                duration_s=round(time.monotonic() - started, 3),
            )
        )
        return output

    async def _run(self, call: ToolCall, context: ToolContext) -> tuple[str, bool]:
        tool = self._tools().get(call.name)
        if tool is None:
            return _error(f"unknown tool {call.name!r}"), False
        missing = [name for name in _required(tool) if name not in call.arguments]
        if missing:
            return _error(f"missing arguments: {', '.join(missing)}"), False
        try:
            async with asyncio.timeout(tool.timeout_s):
                output = await tool.run(call.arguments, context)
        except TimeoutError:
            return _error(f"{tool.name} did not answer within {tool.timeout_s:g} s"), False
        except ToolFailed as failure:
            return _error(str(failure)), False
        except Exception as error:  # a broken tool must not break the conversation
            return _error(f"{tool.name} failed ({type(error).__name__})"), False
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False), True

    def _tools(self) -> dict[str, Tool]:
        found: dict[str, Tool] = {}
        for tool in (*self._fixed, *(t for p in self._providers for t in p.tools())):
            if tool.name in found:
                raise ContractError(f"two tools are named {tool.name!r}")
            found[tool.name] = tool
        return found


def _required(tool: Tool) -> Sequence[str]:
    required = tool.spec.parameters.get("required", ())
    return [str(name) for name in required] if isinstance(required, list | tuple) else []


def _error(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)
