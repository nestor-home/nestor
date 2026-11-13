"""Errors shared by every part of Nestor."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # i18n's types raise these errors
    from nestor.core.i18n.types import Message


class NestorError(Exception):
    """Base class of every error raised by Nestor."""


class ProviderError(NestorError):
    """An external provider (model, speech service, executor…) failed.

    `transient` tells callers whether retrying may succeed (timeout, rate limit) or not
    (bad credentials, unsupported model). `reason`, when given, is what people read of it; the message is for
    developers and logs.
    """

    def __init__(self, provider: str, message: str, *, transient: bool, reason: "Message | None" = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.transient = transient
        self.reason = reason


class CapabilityMissing(NestorError):
    """A required capability is not provided by any plugged component."""

    def __init__(self, capability: str, available: frozenset[str]) -> None:
        listed = ", ".join(sorted(available)) or "none"
        super().__init__(f"capability {capability!r} is required but not available (available: {listed})")
        self.capability = capability


class ContractError(NestorError):
    """Data or a component does not follow its contract (unknown event type, invalid record…)."""
