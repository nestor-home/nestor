"""Runtime: reads the configuration, builds the adapters it names, wires the modules and runs them.

The only layer that knows every module; adapters are found through the `nestor.adapters` entry
point group, so a third-party plugin needs no change here.
"""

from nestor.runtime.app import Nestor
from nestor.runtime.config import ConfigError, NestorConfig, load_config
from nestor.runtime.plugins import (
    AdapterSettings,
    ChannelSettings,
    Distribution,
    Family,
    Plugged,
    Plugin,
    Registry,
    Services,
)

__all__ = [
    "AdapterSettings",
    "ChannelSettings",
    "ConfigError",
    "Distribution",
    "Family",
    "Nestor",
    "NestorConfig",
    "Plugged",
    "Plugin",
    "Registry",
    "Services",
    "load_config",
]
