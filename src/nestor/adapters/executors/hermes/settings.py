"""A Hermes executor as the configuration declares it."""

from pydantic import PositiveFloat, SecretStr

from nestor.adapters.executors.common import INSTRUCTIONS
from nestor.adapters.executors.hermes.executor import HermesExecutor
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class HermesSettings(AdapterSettings):
    base_url: str  # including the API version, e.g. https://hermes.example/v1
    api_key: SecretStr
    model: str  # the Hermes agent profile
    description: str  # what this profile's tools really allow
    instructions: str = INSTRUCTIONS
    timeout_s: PositiveFloat = 15.0
    stop_timeout_s: PositiveFloat = 10.0


def build(settings: HermesSettings, name: str, services: Services) -> HermesExecutor:
    executor = HermesExecutor(
        settings.base_url,
        settings.api_key.get_secret_value(),
        settings.model,
        description=settings.description,
        instructions=settings.instructions,
        timeout_s=settings.timeout_s,
        stop_timeout_s=settings.stop_timeout_s,
    )
    executor.name = name  # two Hermes profiles are two executors
    return executor
