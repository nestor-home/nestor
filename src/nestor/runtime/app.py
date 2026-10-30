"""Nestor assembled from a configuration: storage, journal, agent, tasks, channels, delivery."""

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from typing import Self, cast

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEventLog, SQLiteMemoryStore
from nestor.core import Component, ContractError
from nestor.modules.channels import Channel
from nestor.modules.cognition import ConversationModel, Executor
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.tools import Toolbox, ToolProvider
from nestor.modules.conversation import Agent, ChannelProfile, Persona
from nestor.modules.home import PresenceSource
from nestor.modules.household import Household
from nestor.modules.initiative import Courier, DeliveryPolicy, QuietHours, TaskAnnouncer
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories
from nestor.modules.memory.assistant import MemoryTools
from nestor.runtime.config import AdapterConfig, NestorConfig
from nestor.runtime.plugins import Family, Registry, Services

log = logging.getLogger("nestor")


class Nestor:
    """Build with `Nestor(config)`, then `async with nestor: await nestor.serve()`."""

    def __init__(self, config: NestorConfig, registry: Registry | None = None) -> None:
        self.config = config
        registry = registry or Registry.installed()
        services = Services(data_dir=config.data_dir)

        self.database = SQLiteDatabase(config.data_dir / "nestor.db")
        self.journal = Journal(SQLiteEventLog(self.database))
        self.household = Household(p.to_person() for p in config.household)

        self.model = _build(registry, Family.MODEL, config.model, "model", services, ConversationModel)
        self.executors = [
            _build(registry, Family.EXECUTOR, c, c.name or c.kind, services, Executor) for c in config.executors
        ]
        self.channels = [
            _build(registry, Family.CHANNEL, c, c.name or c.kind, services, Channel) for c in config.channels
        ]
        if len({c.channel_id for c in self.channels}) != len(self.channels):
            raise ContractError("two channels have the same name: give each a distinct `name`")
        self.tools = [_build(registry, Family.TOOLS, c, c.name or c.kind, services, ToolProvider) for c in config.tools]
        self.presence = (
            _build(registry, Family.PRESENCE, config.presence, "presence", services, PresenceSource)
            if config.presence
            else None
        )

        self.tasks = TaskManager(self.journal, self.executors)
        delegation = Delegation(self.tasks)
        self.memories = Memories(self.journal, SQLiteMemoryStore(self.database))
        memory = MemoryTools(self.memories, self.household)
        self.agent = Agent(
            model=self.model,
            persona=Persona(**config.persona.model_dump()),
            journal=self.journal,
            household=self.household,
            toolbox=Toolbox(self.journal, providers=[delegation, memory, *self.tools]),
            channels={c.channel_id: ChannelProfile(c.medium, c.style) for c in self.channels},
            context=[delegation, memory],
        )
        initiative = config.initiative
        self.courier = Courier(
            self.journal,
            self.agent,
            self.channels,
            policy=DeliveryPolicy(
                quiet_hours=QuietHours.parse(initiative.quiet_hours) if initiative.quiet_hours else None,
                main_room=initiative.main_room,
                timezone=config.persona.timezone,
            ),
            presence=self.presence,
            follow_up_after_s=initiative.follow_up_after_s,
        )
        self.announcer = TaskAnnouncer(self.journal, self.household, self.courier)
        self._stack = AsyncExitStack()

    @property
    def components(self) -> Sequence[Component]:
        """In start order; they are closed in reverse."""
        presence = [self.presence] if self.presence else []
        return [
            self.database,
            self.model,
            *self.executors,
            *presence,
            self.tasks,
            *self.channels,
            self.courier,
            self.announcer,
        ]

    async def __aenter__(self) -> Self:
        try:
            for component in self.components:
                await self._stack.enter_async_context(component)
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def serve(self) -> None:
        """Serve every channel until cancelled. A channel that crashes is logged and the others keep going."""
        await asyncio.gather(*(self._serve(channel) for channel in self.channels))

    async def _serve(self, channel: Channel) -> None:
        try:
            await channel.serve(self.agent)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("channel %s stopped", channel.channel_id)


def _build[C](
    registry: Registry, family: Family, config: AdapterConfig, name: str, services: Services, expected: type[C]
) -> C:
    component = registry.get(family, config.kind).create(config.settings(), name, services)
    if not isinstance(component, expected):
        raise ContractError(f"plugin {config.kind!r} built a {type(component).__name__}, not a {expected.__name__}")
    return cast(C, component)


async def run_until_stopped(nestor: Nestor) -> None:
    """Serve until SIGINT/SIGTERM, then close everything cleanly (remote tasks keep running)."""
    import signal

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        await asyncio.wait({serving, asyncio.create_task(stop.wait())}, return_when=asyncio.FIRST_COMPLETED)
        serving.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serving
