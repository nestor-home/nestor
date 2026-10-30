"""Events of the instance itself: its configuration edited, a secret changed, a restart asked for.

Never a value: paths and names only (a configuration value may be personal, a secret's never leaves
the vault)."""

from nestor.core import Event


class ConfigChanged(Event, event_type="config.changed"):
    by: str  # an account id, or "cli"
    changed_paths: tuple[str, ...]  # dotted paths: `channels.0.token`, `persona.name`
    restored: str | None = None  # the history entry it was restored from


class SecretChanged(Event, event_type="secret.changed"):
    name: str
    by: str
    removed: bool = False


class RestartRequested(Event, event_type="system.restart.requested"):
    by: str
