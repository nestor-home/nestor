"""What the tools of a connected account share: the services people name, and how a call that fails reaches the
model."""

from collections.abc import Awaitable

from nestor.adapters.connectors.common.api import StatusError
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import ToolFailed
from nestor.modules.connectors import Service


def service(name: str, *tools: ToolSpec, brand: str | None = None) -> Service:
    """A service of the account, served by `tools`."""
    return Service(name=name, brand=brand, tools=frozenset(t.name for t in tools))


async def ask[T](what: str, call: Awaitable[T]) -> T:
    """What `call` answers; a failure the model can read otherwise (`what` names it: "Google Drive search")."""
    try:
        return await call
    except ProviderError as error:
        raise failed(what, error) from None


def failed(what: str, error: ProviderError) -> ToolFailed:
    """A service's refusal as the model reads it: an id it does not know, a request it refuses, or a failure."""
    if isinstance(error, StatusError) and error.status == 404:
        return ToolFailed(f"{what}: not found, check the id")
    if isinstance(error, StatusError) and error.status == 400:
        return ToolFailed(f"{what}: the service refused the request, check the arguments ({error})")
    return ToolFailed(f"{what} failed: {error}")
