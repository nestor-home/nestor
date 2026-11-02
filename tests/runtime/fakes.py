"""Plugins backed by the test kit's doubles: Nestor assembled without any provider."""

from nestor.modules.channels import Assistant
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry, Services
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ConceptEmbedder, FakeRemote, ScriptedModel, ScriptedRemoteExecutor
from nestor.testing.cognition.model import Reply
from nestor.testing.initiative import Inbox, QueuedSource


class ModelSettings(AdapterSettings):
    replies: tuple[str, ...] = ()


class NoSettings(AdapterSettings):
    pass


class FlakySettings(AdapterSettings):
    crashes: int = 1


class CrashingChannel(InMemoryChannel):
    async def serve(self, assistant: Assistant) -> None:
        raise RuntimeError("socket closed")


class FlakyChannel(InMemoryChannel):
    """Stops with an error the first `crashes` times it is served, then serves."""

    def __init__(self, channel_id: str, crashes: int) -> None:
        super().__init__(channel_id)
        self.crashes = crashes
        self.served = 0

    async def serve(self, assistant: Assistant) -> None:
        self.served += 1
        if self.served <= self.crashes:
            raise RuntimeError("socket closed")
        await super().serve(assistant)


class Fakes:
    """Keeps the built doubles so a test can drive and inspect them."""

    def __init__(self) -> None:
        self.embedder = ConceptEmbedder({"jambon": "meat", "vegetarien": "meat"})
        self.script: list[Reply] = []  # replies of the next model built, when its settings give none
        self.models: list[ScriptedModel] = []
        self.channels: list[InMemoryChannel] = []
        self.remote = FakeRemote()
        self.inbox = Inbox()

    def registry(self) -> Registry:
        flaky = Plugin(Family.CHANNEL, "flaky", FlakySettings, self._flaky)
        crashing = Plugin(Family.CHANNEL, "crashing", NoSettings, lambda s, name, x: CrashingChannel(name))
        inbox = Plugin(Family.INBOUND, "inbox", NoSettings, lambda s, name, x: QueuedSource(self.inbox))
        concepts = Plugin(Family.EMBEDDER, "concepts", NoSettings, lambda s, n, x: self.embedder)
        return Registry(
            [self.model_plugin(), self.channel_plugin(), self.executor_plugin(), crashing, flaky, inbox, concepts]
        )

    def model_plugin(self) -> Plugin[ModelSettings]:
        return Plugin(Family.MODEL, "scripted", ModelSettings, self._model)

    def channel_plugin(self) -> Plugin[NoSettings]:
        return Plugin(Family.CHANNEL, "memory", NoSettings, self._channel)

    def executor_plugin(self) -> Plugin[NoSettings]:
        return Plugin(Family.EXECUTOR, "remote", NoSettings, self.executor)

    def _model(self, settings: ModelSettings, name: str, services: Services) -> ScriptedModel:
        model = ScriptedModel(*(settings.replies or self.script))
        self.models.append(model)
        return model

    def _channel(self, settings: NoSettings, name: str, services: Services) -> InMemoryChannel:
        channel = InMemoryChannel(name)
        self.channels.append(channel)
        return channel

    def _flaky(self, settings: FlakySettings, name: str, services: Services) -> FlakyChannel:
        channel = FlakyChannel(name, settings.crashes)
        self.channels.append(channel)
        return channel

    def executor(self, settings: NoSettings, name: str, services: Services) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(self.remote, duration_s=None)
