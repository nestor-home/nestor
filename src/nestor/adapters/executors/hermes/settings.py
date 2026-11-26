"""A Hermes executor as the configuration declares it."""

from pydantic import PositiveFloat, SecretStr

from nestor.adapters.executors.common import INSTRUCTIONS, ExecutorSettings
from nestor.adapters.executors.hermes.executor import HermesExecutor
from nestor.modules.cognition import Executor
from nestor.runtime import Services


class HermesSettings(ExecutorSettings):
    base_url: str  # including the API version, e.g. https://hermes.example/v1
    api_key: SecretStr
    model: str  # the Hermes agent profile
    description: str  # what this profile's tools really allow
    instructions: str = INSTRUCTIONS
    timeout_s: PositiveFloat = 15.0
    stop_timeout_s: PositiveFloat = 10.0
    nestor_mcp: bool = False  # its profile declares Nestor's MCP server as `nestor`, with this executor's key


def build(settings: HermesSettings, name: str, services: Services) -> Executor:
    executor = HermesExecutor(
        settings.base_url,
        settings.api_key.get_secret_value(),
        settings.model,
        description=settings.description,
        instructions=settings.instructions,
        timeout_s=settings.timeout_s,
        stop_timeout_s=settings.stop_timeout_s,
        nestor_mcp=settings.nestor_mcp,
    )
    return settings.apply(executor, name)  # two Hermes profiles are two executors
