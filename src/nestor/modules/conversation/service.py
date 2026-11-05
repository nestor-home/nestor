"""The central agent: one assistant behind every channel.

For each message it builds the instructions (persona, channel, person, context from other
modules), replays the recent history from the journal, streams the model's answer and runs the
tools it calls, round after round. Everything observable goes to the journal.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from nestor.core import ContractError, PersonId, ProviderError, utc_now
from nestor.core.i18n import Localizer
from nestor.modules.channels import Address, Assistant, Exchange, InboundMessage, Medium, MessageEnd, Reply, Sender
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
from nestor.modules.conversation.conversations import Conversations, Turn
from nestor.modules.conversation.events import AssistantTurn
from nestor.modules.conversation.history import notification_message
from nestor.modules.conversation.persona import Instructions, Persona
from nestor.modules.conversation.ports import ContextProvider, Layer, TurnContext
from nestor.modules.conversation.speakers import Speakers
from nestor.modules.conversation.types import FallbackReason, Notification, ReplyPhase
from nestor.modules.household import Household, Person
from nestor.modules.identity import Heard, Speaker
from nestor.modules.journal import Journal


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    """What the agent needs to know about a channel to write for it, and to tell its conversations apart."""

    style: str = ""
    conversation_ends_after_s: float | None = None  # None: the default of each turn's medium

    def ends_conversation_after_s(self, medium: Medium) -> float:
        return self.conversation_ends_after_s or medium.conversation_ends_after_s


SAID_MESSAGES = 3  # the person's messages a turn looks things up with, as NVIDIA's RAG concatenates them


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """The model that answers in each medium: the voice needs its first words fast, writing allows more.
    `background` runs the turns nobody waits for (a scheduled wake-up): the written one by default."""

    spoken: ConversationModel
    written: ConversationModel
    background: ConversationModel | None = None

    @classmethod
    def single(cls, model: ConversationModel) -> "ModelChoice":
        return cls(spoken=model, written=model)

    def of(self, medium: Medium) -> ConversationModel:
        return self.spoken if medium is Medium.SPOKEN else self.written

    @property
    def unattended(self) -> ConversationModel:
        return self.background or self.written

    def distinct(self) -> tuple[ConversationModel, ...]:
        found: list[ConversationModel] = []
        for model in (self.spoken, self.written, self.unattended):
            if all(model is not other for other in found):
                found.append(model)
        return tuple(found)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSettings:
    max_tool_rounds: int = 6
    history_events: int = 60
    slow_after_s: float = 4.0  # spoken channels say a filler when the first words take longer


class LiveReplies:
    """The answers being produced right now and where each stands. Listeners are called on every
    change, synchronously: they must only take note (what the agent is doing is read from here)."""

    def __init__(self) -> None:
        self._phases: dict[int, ReplyPhase] = {}
        self._listeners: list[Callable[[], object]] = []

    def phases(self) -> tuple[ReplyPhase, ...]:
        return tuple(self._phases.values())

    def listen(self, listener: Callable[[], object]) -> Callable[[], None]:
        """Call `listener` on every change; returns what stops it."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def set(self, reply: object, phase: ReplyPhase | None) -> None:
        """`reply` is now in `phase`; `None` once it is over."""
        before = self._phases.pop(id(reply), None) if phase is None else self._phases.get(id(reply))
        if phase is not None:
            self._phases[id(reply)] = phase
        if before is not phase:
            for listener in tuple(self._listeners):
                listener()


class Agent(Assistant):
    def __init__(
        self,
        *,
        models: ModelChoice,
        persona: Persona,
        journal: Journal,
        household: Household,
        toolbox: Toolbox,
        channels: Mapping[str, ChannelProfile] | None = None,
        localizer: Localizer,
        context: Iterable[ContextProvider] = (),
        speakers: Speakers | None = None,
        settings: AgentSettings | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """`speakers` tells who speaks on shared devices (with recognised voices when it has them); its tools and
        guidance belong in `toolbox` and `context`."""
        self.models, self.persona, self.journal = models, persona, journal
        self.conversations = Conversations(
            journal,
            ends_after_s=lambda address, medium: self.channel(address).ends_conversation_after_s(medium),
            clock=clock,
        )
        self.localizer = localizer
        self.household, self.toolbox = household, toolbox
        self.speakers = speakers or Speakers(journal, household)
        self._channels = dict(channels or {})
        self._context = (self.speakers, *context)  # who speaks: the agent's own concern, on every turn
        self.settings = settings or AgentSettings()
        self.replies = LiveReplies()  # what it is answering right now

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        person = self.household.identify(address.channel, sender.id)
        return person.id if person else None

    def respond(self, message: InboundMessage) -> Reply:
        return AgentReply(self, message.address, message.medium, message)

    @property
    def voice_wait_s(self) -> float | None:
        return self.speakers.wait_s if self.speakers.voices is not None else None

    async def hear(self, audio: bytes) -> Heard | None:
        return await self.speakers.voices.hear(audio) if self.speakers.voices is not None else None

    async def compose(
        self, address: Address, person: Person | None, notification: Notification, medium: Medium
    ) -> tuple[str, ...]:
        """The answer to a notification (a task's result, a watch, a message to pass on) for this conversation, to be
        delivered through `medium` to `person`: a draft, in the persona's voice and with the conversation's
        history. Nothing is logged until it is delivered (`delivered`): a message that could not go out was
        never said."""
        return await AgentReply(self, address, medium, notification, person=person).collect()

    async def delivered(
        self,
        address: Address,
        person: Person | None,
        notification: Notification,
        medium: Medium,
        texts: Sequence[str],
    ) -> Exchange:
        """Record a composed answer once sent: the notification opens a turn of the conversation, as a person's
        message would, and the answer follows it. Replies to it later see both."""
        turn = await self.conversations.turn(address, medium)
        await turn.notified(notification, person.id if person else None)
        for text in texts:
            await turn.answered(text)
        turn.end()
        return turn.exchange

    async def background(self, address: Address, person: Person | None, notification: Notification) -> tuple[str, ...]:
        """Run a turn nobody waits for (a scheduled wake-up), on behalf of `person`, with the agent's tools and
        the background model, without any conversation's history. What it writes reaches no one: to tell
        someone, it uses its tools. Its tool calls are logged as usual."""
        return await AgentReply(self, address, Medium.WRITTEN, notification, person=person, unattended=True).collect()

    def channel(self, address: Address) -> ChannelProfile:
        return self._channels.get(address.channel, ChannelProfile())

    async def instructions(
        self, address: Address, speaker: Speaker, medium: Medium, said: str | None, *, shared: bool = False
    ) -> Instructions:
        """`shared`: the turn comes from a device anyone at home may use (`address.conversation` is its room)."""
        person = self.household.person(speaker.person) if speaker.person else None
        turn = TurnContext(person=person, speaker=speaker, address=address, said=said)
        sections = await asyncio.gather(*(p.context(turn) for p in self._context))
        return self.persona.instructions(
            medium=medium,
            style=self.channel(address).style,
            person=person,
            speaker=speaker,
            room=address.conversation if shared else None,
            now=utc_now(),
            guidance=tuple(g for p in self._context if (g := p.guidance())),
            people=self.household.people,
            household=tuple(text for found in sections if (text := found.get(Layer.HOUSEHOLD))),
            turn=tuple(text for found in sections if (text := found.get(Layer.TURN))),
        )


class AgentReply(Reply):
    """One answer to what opens a turn: a person's message, or a notification of Nestor's. Produced in the background
    and streamed through a queue so that a channel can interrupt it from another task at any time.

    The answer to a message is the conversation's as it goes: each round of the model that writes something is a message
    of its own, logged as soon as it ends, before the tools it asked for run, so the journal keeps the order the user
    saw. A voice channel usually receives a message long before it is played: an interruption that comes after it was
    logged is recorded as an `AnswerCut`, so the history keeps only what the user heard.

    The answer to a notification is a draft, logged with its notification by whoever delivers it (`Agent.delivered`);
    `unattended`, a turn nobody takes part in (a wake-up), without any conversation's history."""

    def __init__(
        self,
        agent: Agent,
        address: Address,
        medium: Medium,
        opening: InboundMessage | Notification,
        *,
        person: Person | None = None,
        unattended: bool = False,
    ) -> None:
        """`person`: whom a notification is for (who sent a message is found when the turn starts)."""
        self._agent, self._address, self._person, self._medium = agent, address, person, medium
        self._speaker = Speaker.account(person.id) if person else Speaker.unknown()
        self._opening = opening
        self._unattended = unattended
        self._chunks: asyncio.Queue[str | MessageEnd | None] = asyncio.Queue()
        self._message: list[str] = []  # the message being written
        self._ended: list[tuple[str, AssistantTurn | None]] = []  # the messages written, logged if recorded
        self._worker: asyncio.Task[None] | None = None
        self._interrupted = False
        self._over = False
        self._turn: Turn | None = None  # the turn this reply writes in, once a message opened it

    async def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
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
        *parts, rest = _share(heard, [text for text, _ in self._ended])
        if self._turn is not None:
            for (text, answer), part in zip(self._ended, parts, strict=True):
                if answer is not None and _letters(part) < _letters(text):
                    await self._turn.cut(answer, part)
            if "".join(self._message).strip() or not self._ended:
                await self._turn.answered(rest, interrupted=True)
        self._message.clear()
        self._end_turn()
        self._chunks.put_nowait(None)

    async def _produce(self) -> None:
        agent = self._agent
        agent.replies.set(self, ReplyPhase.THINKING)
        try:
            opening = self._opening
            if isinstance(opening, InboundMessage):
                self._speaker = await agent.speakers.of(
                    opening, await agent.conversations.current(self._address, self._medium)
                )
                self._person = agent.household.person(self._speaker.person) if self._speaker.person else None
                self._turn = await agent.conversations.turn(self._address, self._medium)
                conversation: str | None = self._turn.exchange.conversation_id
                said = await self._turn.said(opening.text, self._medium, self._speaker)
                agent.speakers.learn(opening.heard, said)
                if phrase := await agent.speakers.enrolling(opening):  # a phrase of a voice being recorded
                    self._say(phrase)
                    await self._end_message()
                    self._end_turn()
                    return
            elif self._unattended:  # a background turn belongs to no conversation
                conversation = None
            else:  # a notification's answer, drafted in the open conversation, if any
                conversation = await agent.conversations.current(self._address, self._medium)
            await self._answer(conversation)
            await self._end_message()
            self._end_turn()
        finally:
            self._agent.replies.set(self, None)
            self._chunks.put_nowait(None)

    async def _answer(self, conversation: str | None) -> None:
        agent = self._agent
        history = await agent.conversations.history(
            self._address, conversation, max_events=agent.settings.history_events, names=agent.speakers.name_of
        )
        opening = self._opening
        if isinstance(opening, Notification):  # not in the journal yet: read as it will be once delivered
            history = (*history, notification_message(opening))
        shared = isinstance(opening, InboundMessage) and opening.sender is None
        said = self._said(history)
        instructions = await agent.instructions(self._address, self._speaker, self._medium, said, shared=shared)
        messages = [
            Message(role=Role.SYSTEM, layers=(instructions.stable, instructions.household), content=instructions.turn),
            *history,
        ]
        exchange = self._turn.exchange if self._turn else None
        context = ToolContext(address=self._address, speaker=self._speaker, exchange=exchange)
        for _ in range(agent.settings.max_tool_rounds):
            try:
                text, calls = await self._round(messages)
            except ProviderError:
                await self._fall_back(FallbackReason.MODEL_UNAVAILABLE)
                return
            await self._end_message(last=not calls)
            if not calls:
                return
            messages.append(Message(role=Role.ASSISTANT, content=text, tool_calls=calls))
            agent.replies.set(self, ReplyPhase.THINKING)
            outputs = await asyncio.gather(*(agent.toolbox.call(call, context) for call in calls))
            messages += [
                Message(role=Role.TOOL, content=o, tool_call_id=c.id) for c, o in zip(calls, outputs, strict=True)
            ]

    def _said(self, history: Sequence[Message]) -> str | None:
        """What a module looks up for this turn: the last messages that opened turns of the conversation (a
        person's, Nestor's notifications), so that a follow-up ("and for her?") keeps its subject."""
        said = [m.content for m in history if m.role is Role.USER][-SAID_MESSAGES:]
        return " ".join(said) or None

    async def _round(self, messages: list[Message]) -> tuple[str, tuple[ToolCall, ...]]:
        """One model call: stream its text out, collect its tool calls."""
        agent = self._agent
        request = ModelRequest(messages=tuple(messages), tools=agent.toolbox.specs())
        text: list[str] = []
        calls: list[ToolCall] = []
        model = agent.models.unattended if self._unattended else agent.models.of(self._medium)
        stream = model.stream(request)
        spoken = self._medium is Medium.SPOKEN
        filler = self._slow_filler() if spoken and not self._message and not self._ended else None
        try:
            async for output in stream:
                if isinstance(output, TextDelta) and output.text:
                    if filler:
                        filler.cancel()
                        filler = None
                    chunk = output.text
                    if not text and self._message and not self._message[-1][-1:].isspace() and not chunk[:1].isspace():
                        chunk = f" {chunk}"  # after a filler: keep the first word apart
                    text.append(chunk)
                    self._say(chunk)
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
        if reason is FallbackReason.MODEL_UNAVAILABLE and self._message:
            self._say(" ")  # keep what was said, then excuse the cut
        agent = self._agent
        self._say(agent.localizer.format(agent.persona.fallback(reason), agent.persona.locale))
        if self._turn is not None:
            await self._turn.fell_back(reason)
        else:
            await agent.conversations.fell_back(self._address, reason)

    def _say(self, text: str) -> None:
        self._message.append(text)
        self._chunks.put_nowait(text)
        if self._turn is not None:  # a draft is only words to send later: still thinking
            self._agent.replies.set(self, ReplyPhase.SPEAKING)

    async def _end_message(self, *, last: bool = True) -> None:
        """The message being written is complete: hand it over and log it (nothing if it is empty).
        `last`: the turn ends with it (no tool call follows)."""
        text, self._message = "".join(self._message).strip(), []
        if not text:
            return
        self._chunks.put_nowait(MessageEnd(last=last))
        self._ended.append((text, await self._turn.answered(text) if self._turn else None))

    def _end_turn(self) -> None:
        """The reply is over, written or cut: the conversation's silence starts now."""
        if not self._over and self._turn is not None:
            self._turn.end()
        self._over = True


def _share(heard: str, messages: list[str]) -> list[str]:
    """What was heard of each message, then of the one being written: the heard words go to each
    message in turn, by length without spaces, since the synthesis may cut words differently."""
    words, parts = heard.split(), []
    for text in messages:
        room, taken = _letters(text), []
        while words and len(words[0]) <= room:
            room -= len(words[0])
            taken.append(words.pop(0))
        parts.append(" ".join(taken))
    return [*parts, " ".join(words)]


def _letters(text: str) -> int:
    return len("".join(text.split()))
