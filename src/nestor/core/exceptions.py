"""Errors shared by every part of Nestor."""


class NestorError(Exception):
    """Base class of every error raised by Nestor."""


class ProviderError(NestorError):
    """An external provider (model, speech service, executor…) failed.

    `transient` tells callers whether retrying may succeed (timeout, rate limit) or not
    (bad credentials, unsupported model).
    """

    def __init__(self, provider: str, message: str, *, transient: bool) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.transient = transient


class CapabilityMissing(NestorError):
    """A required capability is not provided by any plugged component."""

    def __init__(self, capability: str, available: frozenset[str]) -> None:
        listed = ", ".join(sorted(available)) or "none"
        super().__init__(f"capability {capability!r} is required but not available (available: {listed})")
        self.capability = capability


class ContractError(NestorError):
    """Data or a component does not follow its contract (unknown event type, invalid record…)."""
