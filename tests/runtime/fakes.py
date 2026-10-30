"""Plugins backed by the test kit's doubles: Nestor assembled without any provider."""

from nestor.modules.channels import Assistant
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry, Services
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import FakeRemote, ScriptedModel, ScriptedRemoteExecutor
from nestor.testing.cognition.model import Reply


class ModelSettings(AdapterSettings):
    replies: tuple[str, ...] = ()


class NoSettings(AdapterSettings):
    pass


class CrashingChannel(InMemoryChannel):
    async def serve(self, assistant: Assistant) -> None:
        raise RuntimeError("socket closed")


class Fakes:
    """Keeps the built doubles so a test can drive and inspect them."""

    def __init__(self) -> None:
        self.script: list[Reply] = []  # replies of the next model built, when its settings give none
        self.models: list[ScriptedModel] = []
        self.channels: list[InMemoryChannel] = []
        self.remote = FakeRemote()

    def registry(self) -> Registry:
        crashing = Plugin(Family.CHANNEL, "crashing", NoSettings, lambda s, name, x: CrashingChannel(name))
        return Registry([self.model_plugin(), self.channel_plugin(), self.executor_plugin(), crashing])

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

    def executor(self, settings: NoSettings, name: str, services: Services) -> ScriptedRemoteExecutor:
        return ScriptedRemoteExecutor(self.remote, duration_s=None)
