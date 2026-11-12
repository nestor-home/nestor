"""Nestor assembled from a configuration: storage, journal, agent, tasks, channels, delivery."""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Self, cast

from nestor import __version__
from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.adapters.oauth import HttpxTokenEndpoint
from nestor.adapters.releases import HttpReleaseFeed, PipInstaller, probe
from nestor.adapters.storage.file import FileBlobStore
from nestor.adapters.storage.sqlite import (
    GENERATE,
    SQLiteActivityStore,
    SQLiteDatabase,
    SQLiteEpisodeStore,
    SQLiteEventLog,
    SQLiteMemoryStore,
    SQLiteVault,
    SQLiteVectorIndex,
    SQLiteVerifierStore,
)
from nestor.adapters.storage.sqlite.identity import SQLiteVoiceprintStore
from nestor.core import Component, ContractError, Model, ModelType, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.accounts import Accounts
from nestor.modules.activity import ActivityMonitor
from nestor.modules.channels import Channel, SpeechModel, TranscriptionModel
from nestor.modules.cognition import Executor, LanguageModel
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.embedding import EmbeddingModel
from nestor.modules.cognition.tools import Results, Toolbox, ToolProvider
from nestor.modules.connectors import ConnectedInbound, Connections, Connector, ConnectorTools, TokenEndpoint
from nestor.modules.conversation import (
    Agent,
    AgentSettings,
    Attachments,
    ChannelProfile,
    ConversationTitles,
    Mentions,
    ModelChoice,
    Persona,
    Speakers,
)
from nestor.modules.home import Home, PresenceSource, RoomMentions
from nestor.modules.household import Account, Household, Person, SharedAccount
from nestor.modules.identity import Departures, SpeakerModel, Voices
from nestor.modules.initiative import (
    Courier,
    DeliveryPolicy,
    InboundEventSource,
    MessageBook,
    MessageTools,
    Messenger,
    QuietHours,
    Returns,
    ScheduleBook,
    Scheduler,
    ScheduleTools,
    Triage,
    WatchBook,
    WatchKeeper,
)
from nestor.modules.initiative.confirmations import Confirmations
from nestor.modules.initiative.watches.assistant import WatchTools
from nestor.modules.journal import Journal
from nestor.modules.memory import Memories, SearchIndex
from nestor.modules.memory.assistant import MemoryTools
from nestor.modules.memory.episodes import Consolidator, Episodes
from nestor.modules.satellites import Pairing, SatelliteHost
from nestor.modules.system import ReleaseFeed, RestartRequested, Updates
from nestor.runtime.config import AdapterConfig, ComponentConfig, ConfigError, ModelConfig, NestorConfig, ProblemCode
from nestor.runtime.plugins import Family, Plugged, Registry, Services

log = logging.getLogger("nestor")

SECRET_KEY = "NESTOR_SECRET_KEY"
DATABASE = "nestor.db"
BLOBS = "blobs"  # what is too heavy for the journal, by content


def database_path(data_dir: Path) -> Path:
    return data_dir / DATABASE


@dataclass(frozen=True)
class Backoff:
    """How a channel that stopped is served again: after `initial_s`, doubling up to `maximum_s` while it
    keeps failing; a run that lasted `healthy_after_s` starts over from `initial_s`."""

    initial_s: float = 1.0
    maximum_s: float = 60.0
    healthy_after_s: float = 60.0


class Nestor:
    """Build with `Nestor(config)`, then `async with nestor: await nestor.serve()`.

    `environ` is where secrets are read from (the process environment by default); `token_endpoint`
    replaces the HTTP OAuth client (tests use a fake provider), `release_feed` the one read over HTTP;
    `backoff` paces serving a channel again after it stopped.
    """

    def __init__(
        self,
        config: NestorConfig,
        registry: Registry | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        token_endpoint: TokenEndpoint | None = None,
        release_feed: ReleaseFeed | None = None,
        source: Path | None = None,
        backoff: Backoff | None = None,
    ) -> None:
        self.config = config
        self._backoff = backoff or Backoff()
        self.source = source  # the configuration file it was loaded from, when it was (the admin edits it)
        self.registry = registry = registry or Registry.installed()
        self.localizer = FluentLocalizer(catalogue_dirs(["nestor", *registry.packages()]), default=Locale("en"))
        services = Services(data_dir=config.data_dir, localizer=self.localizer, locale=Locale(config.persona.locale))
        self.plugged: list[Plugged] = []  # every adapter built from the configuration, in build order
        environ = os.environ if environ is None else environ
        self.environ: Mapping[str, str] = environ

        self.database = SQLiteDatabase(database_path(config.data_dir))
        self.journal = Journal(SQLiteEventLog(self.database))
        self.restart = Restart(self.journal)
        self.household = _household(config)
        self.accounts = Accounts(
            self.journal, SQLiteVerifierStore(self.database), self.household, SQLiteActivityStore(self.database)
        )

        self.models = models = build_models(config, registry, services, self.plugged)
        services = replace(services, models=lambda key, wanted, path: chosen(models, key, wanted, path))
        roles = config.roles([k for k, m in config.models.items() if m.type is ModelType.LANGUAGE])

        def model(role: str, key: str) -> LanguageModel:
            return chosen(models, key, LanguageModel, tuple(role.split(".")))

        hearing, voicing = config.voice_messages()

        def optional[M: Model](key: str | None, wanted: type[M], role: str) -> M | None:
            return chosen(models, key, wanted, ("agent", role)) if key else None

        self.executors = [
            _build(self.plugged, registry, Family.EXECUTOR, c, c.name or c.plugin, ("executors", i), services, Executor)
            for i, c in enumerate(config.executors)
        ]
        self.channels = [
            _build(self.plugged, registry, Family.CHANNEL, c, c.name or c.plugin, ("channels", i), services, Channel)
            for i, c in enumerate(config.channels)
        ]
        if len({c.channel_id for c in self.channels}) != len(self.channels):
            raise ContractError("two channels have the same name: give each a distinct `name`")
        self.tools = [
            _build(self.plugged, registry, Family.TOOLS, c, c.name or c.plugin, ("tools", i), services, ToolProvider)
            for i, c in enumerate(config.tools)
        ]
        self.inbound = [
            _build(
                self.plugged,
                registry,
                Family.INBOUND,
                c,
                c.name or c.plugin,
                ("inbound", i),
                services,
                InboundEventSource,
            )
            for i, c in enumerate(config.inbound)
        ]
        self.home = (
            _build(self.plugged, registry, Family.HOME, config.home, "home", ("home",), services, Home)
            if config.home
            else None
        )
        self.presence: PresenceSource | None = self.home.presence if self.home else None

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
                    f"{GENERATE} and set it in the environment or the .env next to the configuration, never in the "
                    "configuration file"
                )
            self.token_endpoint = token_endpoint or HttpxTokenEndpoint()
            self.connections = Connections(self.journal, self.vault, self.token_endpoint, self.connectors)
            inbound = ConnectedInbound(self.connections)
            connected = [inbound] if inbound.kinds else []
        self.sources = [*self.inbound, *connected]

        self.pairing = Pairing(self.journal)
        installation = probe()
        self.updates = (
            Updates(
                release_feed or HttpReleaseFeed(config.updates.feed),
                __version__,
                self.journal,
                self.restart.ask,
                installation,
                installer=PipInstaller.found(source, __version__) if source and installation.installable else None,
            )
            if config.updates.check
            else None
        )
        for channel in self.channels:
            if isinstance(channel, SatelliteHost):
                channel.host_satellites(self.pairing, self.journal)
        self.tasks = TaskManager(self.journal, self.executors)
        delegation = Delegation(self.tasks)
        embedder = (
            chosen(models, config.memory.embedder, EmbeddingModel, ("memory", "embedder"))
            if config.memory.embedder
            else None
        )
        voice_model = (
            chosen(models, config.voices.embedder, SpeakerModel, ("voices", "embedder"))
            if config.voices.embedder
            else None
        )
        self.voiceprints = SQLiteVoiceprintStore(self.database)
        self.voices = (
            Voices(voice_model, self.voiceprints, self.journal, settings=config.voices.settings())
            if voice_model is not None
            else None
        )
        locale = Locale(config.persona.locale)
        self.speakers = Speakers(
            self.journal,
            self.household,
            self.voices,
            say=lambda message: self.localizer.format(message, locale),
            wait_s=config.voices.wait_s,
        )
        self.memories, self.episodes, self._memory_parts = assemble_memories(
            self.journal, self.database, embedder, query_timeout_s=config.memory.query_timeout_s
        )
        recall = config.memory.recall()
        memory = MemoryTools(
            self.memories,
            self.episodes,
            self.household,
            self.journal,
            assistant=config.persona.name,
            timezone=config.persona.timezone,
            recall=recall,
        )
        self.watch_book = WatchBook(self.journal, kinds=(k for source in self.sources for k in source.kinds))
        watch_tools = WatchTools(self.watch_book)
        self.message_book = MessageBook(self.journal)
        message_tools = MessageTools(self.message_book, self.household)
        self.schedule_book = ScheduleBook(self.journal, timezone=config.persona.timezone)
        schedule_tools = ScheduleTools(self.schedule_book)
        connector_tools = [ConnectorTools(self.connections)] if self.connections else []
        self.confirmations = Confirmations(self.journal, self.household, self.message_book)
        self.blobs = FileBlobStore(config.data_dir / BLOBS)
        self.toolbox = toolbox = Toolbox(
            self.journal,
            providers=[
                self.speakers,
                delegation,
                memory,
                watch_tools,
                message_tools,
                schedule_tools,
                self.confirmations,
                *self.tools,
                *([self.home.tools] if self.home else []),
                *connector_tools,
            ],
            in_writing=self.confirmations,
            results=Results(self.journal, self.blobs, budget=config.agent.tool_result_chars),
        )
        self.agent = Agent(
            models=ModelChoice(
                spoken=model("agent.spoken", roles["spoken"]),
                written=model("agent.written", roles["written"]),
            ),
            persona=Persona(**{**config.persona.model_dump(), "locale": Locale(config.persona.locale)}),
            localizer=self.localizer,
            journal=self.journal,
            household=self.household,
            toolbox=toolbox,
            channels={
                c.channel_id: ChannelProfile(c.style, c.conversation_ends_after_s, c.sends) for c in self.channels
            },
            context=[delegation, memory, watch_tools, message_tools, schedule_tools, self.confirmations],
            speakers=self.speakers,
            mentions=Mentions(
                [message_tools, *([RoomMentions(self.home)] if self.home else []), delegation, *connector_tools]
            ),
            attachments=Attachments(
                self.blobs,
                transcription=optional(hearing, TranscriptionModel, "transcription"),
                speech=optional(voicing, SpeechModel, "speech"),
            ),
            settings=AgentSettings(
                spoken_tool_wait_s=config.agent.spoken_tool_wait_s, written_tool_wait_s=config.agent.written_tool_wait_s
            ),
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
        self.confirmations.attach(self.courier, lambda call, context: toolbox.call(call, context, confirmed=True))
        self.returns = Returns(self.journal, self.household, self.courier)
        self.messenger = Messenger(self.message_book, self.household, self.courier)
        self.scheduler = Scheduler(self.schedule_book, self.household, self.courier)
        self.watches = WatchKeeper(
            self.watch_book,
            self.household,
            self.courier,
            Triage(model("watches.model", roles["watches"]), language=config.persona.language),
            self.sources,
        )
        self.consolidator = Consolidator(
            self.journal,
            model("memory.consolidation", roles["consolidation"]),
            self.memories,
            self.episodes,
            self.household,
            over_after_s=self.agent.conversations.over_after_s,
            assistant=config.persona.name,
            language=config.persona.language,
            timezone=config.persona.timezone,
            known=config.memory.recent,
        )
        self.titles = ConversationTitles(
            self.journal,
            model("agent.titles", roles["titles"]),
            assistant=config.persona.name,
            language=config.persona.language,
        )
        self.activity = ActivityMonitor(
            self.journal, self.agent.replies, self.tasks, quiet_hours=quiet_hours, timezone=config.persona.timezone
        )
        self._stack = AsyncExitStack()

    def satellite_url(self, seen_as: str) -> str | None:
        """Where devices reach the first host that serves satellites (for pairing URIs), if any."""
        hosts = (c for c in self.channels if isinstance(c, SatelliteHost))
        return next((url for host in hosts if (url := host.satellite_url(seen_as))), None)

    def spoken_channels(self) -> frozenset[str]:
        """The ids of the channels people speak through: their conversations are rooms."""
        return frozenset(c.channel_id for c in self.channels if c.spoken)

    def heard_rooms(self) -> frozenset[str] | None:
        """Rooms a spoken channel can hear right now; `None` without any spoken channel to tell."""
        spoken = [c.rooms for c in self.channels if c.spoken]
        return frozenset().union(*spoken) if spoken else None

    @property
    def components(self) -> Sequence[Component]:
        """In start order; they are closed in reverse."""
        home = [self.home] if self.home else []
        connections = [self.token_endpoint, self.connections] if self.token_endpoint and self.connections else []
        vault = [self.vault] if self.vault else []
        updates = [self.updates] if self.updates else []
        voices = [self.voices] if self.voices else []
        return [
            self.database,
            *vault,
            self.accounts.verifiers,
            self.accounts.activity,
            self.accounts,
            self.pairing,
            *connections,
            *self.models.values(),
            *self._memory_parts,  # after its embedder
            self.voiceprints,
            Departures(self.voiceprints, self.journal, [p.id for p in self.household.people]),  # after its store
            *voices,  # after its model, its store, and who left
            self.speakers,
            *self.executors,
            *self.tools,
            *home,  # its presence and its tools
            self.toolbox,  # after its tools: its calls in the background stop first
            self.tasks,
            *self.channels,
            self.courier,
            self.returns,
            self.message_book,
            self.messenger,
            self.confirmations,
            self.schedule_book,
            self.scheduler,
            self.watch_book,
            *self.sources,
            self.watches,
            self.activity,
            self.titles,
            self.consolidator,
            *updates,
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
        """Serve every channel until cancelled. A channel that stops is logged and served again after a
        pause (the others keep going)."""
        await asyncio.gather(*(self._serve(channel) for channel in self.channels))

    async def _serve(self, channel: Channel) -> None:
        loop = asyncio.get_running_loop()
        delay = self._backoff.initial_s
        while True:
            started = loop.time()
            try:
                await channel.serve(self.agent)
            except asyncio.CancelledError:
                raise
            except ProviderError as error:
                log.warning("channel %s stopped: %s", channel.channel_id, error)
            except Exception:
                log.exception("channel %s stopped", channel.channel_id)
            else:
                return  # it ends when closed
            if loop.time() - started >= self._backoff.healthy_after_s:
                delay = self._backoff.initial_s
            log.info("channel %s serves again in %.1f s", channel.channel_id, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff.maximum_s)


def _household(config: NestorConfig) -> Household:
    """The household of the configuration; an account two people claim is located at the second one."""
    try:
        return Household(p.to_person() for p in config.household)
    except SharedAccount as error:
        claims = [
            ("household", i, "accounts", j)
            for i, person in enumerate(config.household)
            for j, account in enumerate(person.accounts)
            if Account.parse(account) == error.account
        ]
        raise ConfigError(
            str(error),
            path=claims[1],
            code=ProblemCode.SHARED_ACCOUNT,
        ) from None


def _connectors(
    plugged: list[Plugged], registry: Registry, config: NestorConfig, services: Services
) -> list[Connector]:
    """The configured connectors; by default every installed one when the admin is on (it is where they are used)."""
    if config.connectors is not None:
        chosen = config.connectors
    elif config.admin is not None:
        chosen = tuple(AdapterConfig(kind=kind) for kind in registry.ids(Family.CONNECTOR))
    else:
        chosen = ()
    connectors = [
        _build(plugged, registry, Family.CONNECTOR, c, c.name or c.plugin, ("connectors", i), services, Connector)
        for i, c in enumerate(chosen)
    ]
    kinds = [c.info.kind for c in connectors]
    if len(set(kinds)) != len(kinds):
        raise ContractError("two connectors declare the same kind: configure each service once")
    return connectors


# why a model of another type is refused where one of a type is wanted
_REFUSED: Mapping[ModelType, tuple[ProblemCode, str]] = {
    ModelType.LANGUAGE: (ProblemCode.NOT_ANSWERING, "cannot answer; choose a language model"),
    ModelType.EMBEDDING: (ProblemCode.NOT_EMBEDDING, "cannot search memories; choose a text embedding model"),
    ModelType.SPEAKER: (ProblemCode.NOT_SPEAKER, "cannot tell voices apart; choose a speaker recognition model"),
    ModelType.TRANSCRIPTION: (ProblemCode.NOT_TRANSCRIBING, "cannot transcribe speech; choose a transcription model"),
    ModelType.SPEECH: (ProblemCode.NOT_SPEAKING, "cannot speak; choose a speech model"),
}


def chosen[M: Model](models: Mapping[str, Model], key: str, wanted: type[M], path: tuple[str | int, ...]) -> M:
    """The model `key` names where the configuration, at `path`, wants one of type `wanted`."""
    where = ".".join(map(str, path))
    found = models.get(key)
    if found is None:
        known = ", ".join(models) or "none"
        raise ConfigError(
            f"{where}: no model named {key!r} in models ({known})",
            path=path,
            code=ProblemCode.UNKNOWN_MODEL,
            detail=key,
        )
    if not isinstance(found, wanted):
        code, why = _REFUSED[wanted.type]
        raise ConfigError(f"{where}: {key} {why}", path=path, code=code, detail=key)
    return found


def build_models(
    config: NestorConfig, registry: Registry, services: Services, plugged: list[Plugged] | None = None
) -> dict[str, Model]:
    """Every model of `models`, built but not started, of the type its configuration says."""
    built: dict[str, Model] = {}
    for key, profile in config.models.items():
        model = _build(
            plugged if plugged is not None else [],
            registry,
            Family.MODEL,
            profile,
            key,
            ("models", key),
            services,
            registry.get(Family.MODEL, profile.plugin).serves or Model,
        )
        built[key] = model
    return built


def _build[C](
    plugged: list[Plugged],
    registry: Registry,
    family: Family,
    config: ComponentConfig | ModelConfig,
    name: str,
    where: tuple[str | int, ...],
    services: Services,
    expected: type[C],
) -> C:
    """The adapter `config` describes, named `name`, at `where` in the configuration."""
    try:
        component = registry.get(family, config.plugin).create(config.settings(), name, services)
    except ConfigError as error:  # what its settings name, located in the whole document
        path = (*where, *error.path)
        raise ConfigError(
            f"{'.'.join(map(str, where))}.{error}", path=path, code=error.code, detail=error.detail
        ) from None
    if not isinstance(component, expected):
        raise ContractError(f"plugin {config.plugin!r} built a {type(component).__name__}, not a {expected.__name__}")
    plugged.append(Plugged(family, config.plugin, name, component, registry.origin(family, config.plugin)))
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


def assemble_memories(
    journal: Journal, database: SQLiteDatabase, embedder: EmbeddingModel | None, *, query_timeout_s: float = 1.0
) -> tuple[Memories, Episodes, tuple[Component, ...]]:
    """The memories and episodes as every instance keeps them, and the components they need started (the vector
    index and the search indexes when there is an embedder, after it)."""
    store, episode_store = SQLiteMemoryStore(database), SQLiteEpisodeStore(database)
    if embedder is None:
        return Memories(journal, store), Episodes(journal, episode_store), ()
    vectors = SQLiteVectorIndex(database)
    memory_index = SearchIndex("memory", store, embedder, vectors, query_timeout_s=query_timeout_s)
    episode_index = SearchIndex("episode", episode_store, embedder, vectors, query_timeout_s=query_timeout_s)
    return (
        Memories(journal, store, memory_index),
        Episodes(journal, episode_store, episode_index),
        (vectors, memory_index, episode_index),
    )


@contextlib.asynccontextmanager
async def open_memories(
    data_dir: Path, embedder: EmbeddingModel | None = None, *, query_timeout_s: float = 1.0
) -> AsyncGenerator[tuple[Memories, Episodes]]:
    """The memories and episodes kept in `data_dir`, assembled and searched as a running instance does (the
    `embedder` is started by the caller), without the rest of Nestor: a bench measures recall on them."""
    database = SQLiteDatabase(database_path(data_dir))
    async with database, AsyncExitStack() as stack:
        memories, episodes, parts = assemble_memories(
            Journal(SQLiteEventLog(database)), database, embedder, query_timeout_s=query_timeout_s
        )
        for part in parts:
            await stack.enter_async_context(part)
        yield memories, episodes


class Restart:
    """A restart asked for by a person (never automatically): Nestor stops as on SIGTERM — channels close,
    remote tasks detach and are followed again after — then the command line re-executes itself.
    `ask` is the one way in: from the admin, the command line, or once a release is installed."""

    def __init__(self, journal: Journal, stop: Callable[[], None] | None = None, *, delay_s: float = 0.2) -> None:
        self.requested = False
        self.stop = stop or (lambda: os.kill(os.getpid(), signal.SIGTERM))
        self._journal, self._delay_s = journal, delay_s

    async def ask(self, by: str) -> None:
        """Journal who asked (an account id, or "cli"), then stop once the answer saying so is sent."""
        await self._journal.publish(RestartRequested(source="system", by=by))
        asyncio.get_running_loop().call_later(self._delay_s, self.request)

    def request(self) -> None:
        self.requested = True
        self.stop()


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
