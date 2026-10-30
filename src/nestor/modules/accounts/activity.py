"""When accounts were last seen: their last sign-in or authenticated request, outside the journal.

A request is not an event worth journaling; the moment is kept, and written at most once a minute per
account, so a busy browser costs nothing.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime

from nestor.core import Component


class ActivityStore(Component, ABC):
    """Contract (checked by `nestor.testing.accounts.ActivityStoreContract`): `record` keeps the latest
    moment per account (an older one never replaces a newer one); `seen` returns them all."""

    @abstractmethod
    async def record(self, account_id: str, at: datetime) -> None: ...

    @abstractmethod
    async def seen(self) -> Mapping[str, datetime]: ...
