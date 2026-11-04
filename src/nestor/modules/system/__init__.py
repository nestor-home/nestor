"""The instance itself: its configuration edited from the admin or the command line, its secrets, its
restarts, and the releases newer than the one it runs. The configuration file is the runtime's."""

from nestor.modules.system.events import (
    ConfigChanged,
    RestartRequested,
    SecretChanged,
    UpdateFailed,
    UpdateRequested,
)
from nestor.modules.system.ports import Installer, ReleaseFeed
from nestor.modules.system.types import (
    Change,
    ChangeKind,
    Installation,
    InstallKind,
    Release,
    Releases,
    version_key,
)
from nestor.modules.system.updates import Updates

__all__ = [
    "Change",
    "ChangeKind",
    "ConfigChanged",
    "InstallKind",
    "Installation",
    "Installer",
    "Release",
    "ReleaseFeed",
    "Releases",
    "RestartRequested",
    "SecretChanged",
    "UpdateFailed",
    "UpdateRequested",
    "Updates",
    "version_key",
]
