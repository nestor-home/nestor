"""The instance itself: its configuration edited from the admin or the command line, its secrets, its
restarts. Only events live here; the configuration file is the runtime's."""

from nestor.modules.system.events import ConfigChanged, RestartRequested, SecretChanged

__all__ = ["ConfigChanged", "RestartRequested", "SecretChanged"]
