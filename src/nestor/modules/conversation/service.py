"""The central agent: one assistant behind every channel.

For each message it builds the instructions (persona, channel, person, context from other
modules), replays the recent history from the journal, streams the model's answer and runs the
tools it calls, round after round. Everything observable goes to the journal.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass

from nestor.core import ContractError, PersonId, ProviderError, utc_now
from nestor.modules.channels import Address, Assistant, InboundMessage, Medium, Reply, Sender
from nestor.modules.cognition.model import (
    ConversationModel,
    Finished,
    FinishReason,
    Message,
    ModelRequest,
    Role,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)
from nestor.modules.cognition.tools import Toolbox, ToolContext
from nestor.modules.conversation.events import AnswerCut, AssistantTurn, FallbackSpoken, UserTurn
from nestor.modules.conversation.history import recent_history
from nestor.modules.conversation.persona import Persona
from nestor.modules.conversation.ports import ContextProvider
from nestor.modules.conversation.types import FallbackReason
from nestor.modules.household import Household, Person
from nestor.modules.journal import Journal


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    """What the agent needs to know about a channel to write for it."""

    medium: Medium = Medium.WRITTEN
    style: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSettings:
    max_tool_rounds: int = 6
    history_events: int = 60
    slow_after_s: float = 4.0  # spoken channels say a filler when the first words take longer


class Agent(Assistant):
    def __init__(
        self,
        *,
        model: ConversationModel,
        persona: Persona,
        journal: Journal,
        household: Household,
        toolbox: Toolbox,
        channels: Mapping[str, ChannelProfile] | None = None,
        context: Iterable[ContextProvider] = (),
        settings: AgentSettings | None = None,
    ) -> None:
        self.model, self.persona, self.journal = model, persona, journal
        self.household, self.toolbox = household, toolbox
        self._channels = dict(channels or {})
        self._context = tuple(context)
        self.settings = settings or AgentSettings()

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        person = self.household.identify(address.channel, sender.id)
        return person.id if person else None

    def respond(self, message: InboundMessage) -> Reply:
        person = self.household.identify(message.address.channel, message.sender.id)
        return AgentReply(self, message.address, person, user=message.text)

    async def compose(self, address: Address, person: Person | None, instruction: str) -> str:
        """Write an unprompted message for this conversation (a task result, an announcement).

        `instruction` tells the agent what to convey; the text is written in the persona's voice,
        with the conversation's history, and logged as an assistant turn like any answer.
        """
        return await AgentReply(self, address, person, instruction=instruction).collect()

    def channel(self, address: Address) -> ChannelProfile:
        return self._channels.get(address.channel, ChannelProfile())

    async def instructions(self, address: Address, person: Person | None) -> str:
        sections = await asyncio.gather(*(p.context(person, address) for p in self._context))
        profile = self.channel(address)
        return self.persona.instructions(
            medium=profile.medium,
            style=profile.style,
            person=person,
            now=utc_now(),
            sections=tuple(s for s in sections if s),
        )


class AgentReply(Reply):
    """One answer, produced in the background and streamed through a queue so that a channel can
    interrupt it from another task at any time.

    A voice channel usually receives the whole text long before it is played: an interruption that
    comes after the answer was logged is recorded as an `AnswerCut`, so the history keeps only
    what the user heard.
    """

    def __init__(
        self,
        agent: Agent,
        address: Address,
        person: Person | None,
        *,
        user: str | None = None,
        instruction: str | None = None,
    ) -> None:
        self._agent, self._address, self._person = agent, address, person
        self._user, self._instruction = user, instruction
        self._chunks: asyncio.Queue[str | None] = asyncio.Queue()
        self._said: list[str] = []
        self._worker: asyncio.Task[None] | None = None
        self._interrupted = False
        self._logged: AssistantTurn | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        if self._worker is not None:
            raise ContractError("a reply can only be read once")
        self._worker = asyncio.create_task(self._produce(), name=f"reply {self._address}")
        while (chunk := await self._chunks.get()) is not None:
            yield chunk
        if not self._interrupted:
            await self._worker  # surface a bug in the agent instead of ending silently

    async def interrupt(self, heard: str) -> None:
        if self._interrupted:
            return
        self._interrupted = True
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        if self._logged is None:
            await self._log_answer(heard, interrupted=True)
        else:
            await self._agent.journal.publish(
                AnswerCut(source="agent", session=self._address.session, turn=self._logged.id, heard=heard)
            )
        self._chunks.put_nowait(None)

    async def _produce(self) -> None:
        try:
            if self._user is not None:
                await self._agent.journal.publish(
                    UserTurn(
                        source="agent",
                        session=self._address.session,
                        address=self._address,
                        text=self._user,
                        person=self._person.id if self._person else None,
                    )
                )
            await self._answer()
            await self._log_answer("".join(self._said), interrupted=False)
        finally:
            self._chunks.put_nowait(None)

    async def _answer(self) -> None:
        agent = self._agent
        messages = [
            Message(role=Role.SYSTEM, content=await agent.instructions(self._address, self._person)),
            *await recent_history(agent.journal, self._address, max_events=agent.settings.history_events),
        ]
        if self._instruction is not None:
            messages.append(Message(role=Role.SYSTEM, content=self._instruction))
        context = ToolContext(address=self._address, person=self._person.id if self._person else None)
        for _ in range(agent.settings.max_tool_rounds):
            try:
                text, calls = await self._round(messages)
            except ProviderError:
                await self._fall_back(FallbackReason.MODEL_UNAVAILABLE)
                return
            if not calls:
                return
            messages.append(Message(role=Role.ASSISTANT, content=text, tool_calls=calls))
            outputs = await asyncio.gather(*(agent.toolbox.call(call, context) for call in calls))
            messages += [
                Message(role=Role.TOOL, content=o, tool_call_id=c.id) for c, o in zip(calls, outputs, strict=True)
            ]

    async def _round(self, messages: list[Message]) -> tuple[str, tuple[ToolCall, ...]]:
        """One model call: stream its text out, collect its tool calls."""
        agent = self._agent
        request = ModelRequest(messages=tuple(messages), tools=agent.toolbox.specs())
        text: list[str] = []
        calls: list[ToolCall] = []
        stream = agent.model.stream(request)
        spoken = agent.channel(self._address).medium is Medium.SPOKEN
        filler = self._slow_filler() if spoken and not self._said else None
        try:
            async for output in stream:
                if isinstance(output, TextDelta) and output.text:
                    if filler:
                        filler.cancel()
                        filler = None
                    text.append(output.text)
                    self._say(output.text)
                elif isinstance(output, ToolCallRequested):
                    calls.append(output.call)
                elif isinstance(output, Finished) and output.reason is not FinishReason.TOOL_CALLS:
                    calls.clear()  # a model that stops without asking for tools is done
        finally:
            if filler:
                filler.cancel()
            await stream.aclose()
        return "".join(text), tuple(calls)

    def _slow_filler(self) -> asyncio.Task[None]:
        async def wait_then_say() -> None:
            await asyncio.sleep(self._agent.settings.slow_after_s)
            await self._fall_back(FallbackReason.MODEL_SLOW)

        return asyncio.create_task(wait_then_say())

    async def _fall_back(self, reason: FallbackReason) -> None:
        if reason is FallbackReason.MODEL_UNAVAILABLE and self._said:
            self._say(" ")  # keep what was said, then excuse the cut
        self._say(self._agent.persona.fallback(reason))
        await self._agent.journal.publish(
            FallbackSpoken(source="agent", session=self._address.session, address=self._address, reason=reason)
        )

    def _say(self, text: str) -> None:
        self._said.append(text)
        self._chunks.put_nowait(text)

    async def _log_answer(self, text: str, *, interrupted: bool) -> None:
        turn = AssistantTurn(
            source="agent", session=self._address.session, address=self._address, text=text, interrupted=interrupted
        )
        await self._agent.journal.publish(turn)
        self._logged = turn
