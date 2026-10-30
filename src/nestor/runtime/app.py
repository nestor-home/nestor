"""Nestor assembled from a configuration: storage, journal, agent, tasks, channels, delivery."""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Self, cast

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.adapters.oauth import HttpxTokenEndpoint
from nestor.adapters.storage.sqlite import (
    SQLiteActivityStore,
    SQLiteDatabase,
    SQLiteEventLog,
    SQLiteMemoryStore,
    SQLiteVault,
    SQLiteVerifierStore,
)
from nestor.adapters.storage.sqlite.vault import GENERATE
from nestor.core import Component, ContractError
from nestor.core.i18n import Locale
from nestor.modules.accounts import Accounts
from nestor.modules.activity import ActivityMonitor
from nestor.modules.channels import Channel
from nestor.modules.cognition import ConversationModel, Executor
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.tools import Toolbox, ToolProvider
from nestor.modules.connectors import ConnectedInbound, Connections, Connector, ConnectorTools, TokenEndpoint
from nestor.modules.conversation import Agent, ChannelProfile, Persona
from nestor.modules.home import PresenceSource
from nestor.modules.household import Household, Person
from nestor.modules.initiative import (
    Courier,
    DeliveryPolicy,
    InboundEventSource,
    QuietHours,
    TaskAnnouncer,
    Triage,
    WatchBook,
    WatchKeeper,
)
from nestor.modules.initiative.watches.assistant import WatchTools
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.satellites import Pairing, SatelliteHost
from nestor.runtime.config import AdapterConfig, ConfigError, NestorConfig
from nestor.runtime.plugins import Family, Plugged, Registry, Services

log = logging.getLogger("nestor")

SECRET_KEY = "NESTOR_SECRET_KEY"
DATABASE = "nestor.db"


def database_path(data_dir: Path) -> Path:
    return data_dir / DATABASE


class Nestor:
    """Build with `Nestor(config)`, then `async with nestor: await nestor.serve()`.

    `environ` is where secrets are read from (the process environment by default); `token_endpoint`
    replaces the HTTP OAuth client (tests use a fake provider).
    """

    def __init__(
        self,
        config: NestorConfig,
        registry: Registry | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        token_endpoint: TokenEndpoint | None = None,
        source: Path | None = None,
    ) -> None:
        self.config = config
        self.source = source  # the configuration file it was loaded from, when it was (the admin edits it)
        self.registry = registry = registry or Registry.installed()
        self.restart = Restart()
        self.localizer = FluentLocalizer(catalogue_dirs(["nestor", *registry.packages()]), default=Locale("en"))
        services = Services(data_dir=config.data_dir, localizer=self.localizer, locale=Locale(config.persona.locale))
        self.plugged: list[Plugged] = []  # every adapter built from the configuration, in build order
        environ = os.environ if environ is None else environ
        self.environ: Mapping[str, str] = environ

        self.database = SQLiteDatabase(database_path(config.data_dir))
        self.journal = Journal(SQLiteEventLog(self.database))
        self.household = Household(p.to_person() for p in config.household)
        self.accounts = Accounts(
            self.journal, SQLiteVerifierStore(self.database), self.household, SQLiteActivityStore(self.database)
        )

        self.model = _build(self.plugged, registry, Family.MODEL, config.model, "model", services, ConversationModel)
        self.executors = [
            _build(self.plugged, registry, Family.EXECUTOR, c, c.name or c.kind, services, Executor)
            for c in config.executors
        ]
        self.channels = [
            _build(self.plugged, registry, Family.CHANNEL, c, c.name or c.kind, services, Channel)
            for c in config.channels
        ]
        if len({c.channel_id for c in self.channels}) != len(self.channels):
            raise ContractError("two channels have the same name: give each a distinct `name`")
        self.tools = [
            _build(self.plugged, registry, Family.TOOLS, c, c.name or c.kind, services, ToolProvider)
            for c in config.tools
        ]
        self.triage_model = (
            _build(
                self.plugged, registry, Family.MODEL, config.triage_model, "triage-model", services, ConversationModel
            )
            if config.triage_model
            else self.model
        )
        self.inbound = [
            _build(self.plugged, registry, Family.INBOUND, c, c.name or c.kind, services, InboundEventSource)
            for c in config.inbound
        ]
        self.presence = (
            _build(self.plugged, registry, Family.PRESENCE, config.presence, "presence", services, PresenceSource)
            if config.presence
            else None
        )

        self.connectors = _connectors(self.plugged, registry, config, services)
        self.token_endpoint: TokenEndpoint | None = None
        self.connections: Connections | None = None
        connected: list[InboundEventSource] = []
        secret = environ.get(SECRET_KEY)
        # the vault: connectors' tokens and the configuration's secrets; without the instance key, neither
        self.vault = SQLiteVault(self.database, secret) if secret else None
        if self.connectors:
            if self.vault is None:
                raise ConfigError(
                    f"{SECRET_KEY} is not set: connectors keep their tokens encrypted with it. Generate one with "
                    f"{GENERATE} and set it in the environment, never in the configuration file"
                )
            self.token_endpoint = token_endpoint or HttpxTokenEndpoint()
            self.connections = Connections(self.journal, self.vault, self.token_endpoint, self.connectors)
            inbound = ConnectedInbound(self.connections)
            connected = [inbound] if inbound.kinds else []
        self.sources = [*self.inbound, *connected]

        self.pairing = Pairing(self.journal)
        for channel in self.channels:
            if isinstance(channel, SatelliteHost):
                channel.host_satellites(self.pairing, self.journal)
        self.tasks = TaskManager(self.journal, self.executors)
        delegation = Delegation(self.tasks)
        self.memories = Memories(self.journal, SQLiteMemoryStore(self.database))
        memory = MemoryTools(self.memories, self.household)
        self.watch_book = WatchBook(self.journal, kinds=(k for source in self.sources for k in source.kinds))
        watch_tools = WatchTools(self.watch_book)
        connector_tools = [ConnectorTools(self.connections)] if self.connections else []
        self.agent = Agent(
            model=self.model,
            persona=Persona(**{**config.persona.model_dump(), "locale": Locale(config.persona.locale)}),
            localizer=self.localizer,
            journal=self.journal,
            household=self.household,
            toolbox=Toolbox(self.journal, providers=[delegation, memory, watch_tools, *self.tools, *connector_tools]),
            channels={c.channel_id: ChannelProfile(c.medium, c.style) for c in self.channels},
            context=[delegation, memory, watch_tools],
        )
        initiative = config.initiative
        quiet_hours = QuietHours.parse(initiative.quiet_hours) if initiative.quiet_hours else None
        self.courier = Courier(
            self.journal,
            self.agent,
            self.channels,
            policy=DeliveryPolicy(
                quiet_hours=quiet_hours,
                main_room=initiative.main_room,
                timezone=config.persona.timezone,
            ),
            presence=self.presence,
            follow_up_after_s=initiative.follow_up_after_s,
        )
        self.announcer = TaskAnnouncer(self.journal, self.household, self.courier)
        self.watches = WatchKeeper(
            self.watch_book,
            self.household,
            self.courier,
            Triage(self.triage_model, language=config.persona.language),
            self.sources,
        )
        self.activity = ActivityMonitor(
            self.journal, self.agent.replies, self.tasks, quiet_hours=quiet_hours, timezone=config.persona.timezone
        )
        self._stack = AsyncExitStack()

    @property
    def components(self) -> Sequence[Component]:
        """In start order; they are closed in reverse."""
        presence = [self.presence] if self.presence else []
        triage = [self.triage_model] if self.triage_model is not self.model else []
        connections = [self.token_endpoint, self.connections] if self.token_endpoint and self.connections else []
        vault = [self.vault] if self.vault else []
        return [
            self.database,
            *vault,
            self.accounts.verifiers,
            self.accounts.activity,
            self.accounts,
            self.pairing,
            *connections,
            self.model,
            *triage,
            *self.executors,
            *self.tools,
            *presence,
            self.tasks,
            *self.channels,
            self.courier,
            self.announcer,
            self.watch_book,
            *self.sources,
            self.watches,
            self.activity,
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


def _connectors(
    plugged: list[Plugged], registry: Registry, config: NestorConfig, services: Services
) -> list[Connector]:
    """The configured connectors; by default every installed one when the admin is on (it is where they are used)."""
    if config.connectors is not None:
        chosen = config.connectors
    elif config.admin is not None:
        chosen = tuple(AdapterConfig(kind=kind) for kind in registry.kinds(Family.CONNECTOR))
    else:
        chosen = ()
    connectors = [_build(plugged, registry, Family.CONNECTOR, c, c.name or c.kind, services, Connector) for c in chosen]
    kinds = [c.info.kind for c in connectors]
    if len(set(kinds)) != len(kinds):
        raise ContractError("two connectors declare the same kind: configure each service once")
    return connectors


def _build[C](
    plugged: list[Plugged],
    registry: Registry,
    family: Family,
    config: AdapterConfig,
    name: str,
    services: Services,
    expected: type[C],
) -> C:
    component = registry.get(family, config.kind).create(config.settings(), name, services)
    if not isinstance(component, expected):
        raise ContractError(f"plugin {config.kind!r} built a {type(component).__name__}, not a {expected.__name__}")
    plugged.append(Plugged(family, config.kind, name, component, registry.origin(family, config.kind)))
    return cast(C, component)


@contextlib.asynccontextmanager
async def open_accounts(data_dir: Path, people: Iterable[Person]) -> AsyncGenerator[Accounts]:
    """The account book kept in `data_dir`, without the rest of Nestor (for the command line: a running
    instance sees the change at its next start)."""
    database = SQLiteDatabase(database_path(data_dir))
    accounts = Accounts(
        Journal(SQLiteEventLog(database)),
        SQLiteVerifierStore(database),
        Household(people),
        SQLiteActivityStore(database),
    )
    async with database, accounts:
        yield accounts


class Restart:
    """A restart asked for by a person (never automatically): Nestor stops as on SIGTERM — channels close,
    remote tasks detach and are followed again after — then the command line re-executes itself."""

    def __init__(self, stop: Callable[[], None] | None = None) -> None:
        self.requested = False
        self._stop = stop or (lambda: os.kill(os.getpid(), signal.SIGTERM))

    def request(self) -> None:
        self.requested = True
        self._stop()


async def run_until_stopped(nestor: Nestor, extras: Sequence[Component] = ()) -> None:
    """Serve until SIGINT/SIGTERM, then close everything cleanly (remote tasks keep running).

    `extras` run alongside, started once Nestor is and closed before it (the admin web server)."""
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    async with nestor, AsyncExitStack() as stack:
        for extra in extras:
            await stack.enter_async_context(extra)
        serving = asyncio.create_task(nestor.serve())
        await asyncio.wait({serving, asyncio.create_task(stop.wait())}, return_when=asyncio.FIRST_COMPLETED)
        serving.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serving
