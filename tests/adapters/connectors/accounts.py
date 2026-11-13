"""What the tests of account connectors share: the access a connection lends, a tool call's context."""

from collections.abc import Mapping

from nestor.core import PersonId, ProviderError
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext
from nestor.modules.connectors import Access, Secrets
from nestor.modules.identity import Speaker

MATHIS = PersonId("mathis")
CONTEXT = ToolContext(address=Address("telegram", "42"), speaker=Speaker.account(MATHIS))
TOKEN = "ya29.a0AfB_sentinel-access-token"


class FakeAccess(Access):
    """The connection's access as Connections lends it: a token (or a refusal), durable state."""

    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.refusals = 0  # next token() calls that fail as a revoked authorisation does
        self.token_calls = 0

    async def revoked(self) -> None:
        raise AssertionError("not reached: no service refuses a fresh token here")

    async def token(self, *, refused: str | None = None) -> str:
        self.token_calls += 1
        if self.refusals:
            self.refusals -= 1
            raise ProviderError("google", "authorisation expired: connect again", transient=False)
        return TOKEN

    async def secrets(self) -> Secrets:
        return {}

    async def load_state(self) -> Mapping[str, str]:
        return dict(self.state)

    async def save_state(self, state: Mapping[str, str]) -> None:
        self.state = dict(state)
