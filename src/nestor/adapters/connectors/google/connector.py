"""The Google connector: Gmail (read only, and new mail for watches), Calendar, Drive (read only), Contacts (read
only) and Tasks of each connected account."""

from collections.abc import Sequence
from typing import Any

from nestor.adapters.connectors.common.accounts import AccountConnector
from nestor.adapters.connectors.common.tools import service
from nestor.adapters.connectors.google import calendar, contacts, drive, gmail, tasks
from nestor.adapters.connectors.google.api import GmailApi, new_client
from nestor.adapters.connectors.google.inbound import GmailInbound
from nestor.core import ProviderError
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import Access, AuthKind, Connection, ConnectorInfo, OAuthSpec

SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/tasks",
)


INFO = ConnectorInfo(
    kind="google",
    brand="google",
    title=Message.of("connector-google-title"),
    description=Message.of("connector-google-description"),
    auth=AuthKind.OAUTH2,
    oauth=OAuthSpec(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        scopes=SCOPES,
        extra_authorize={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
        client_credentials=True,
    ),
    setup=Message.of("connector-google-setup"),
    inbound=("mail",),
    services=(
        service("gmail", gmail.SEARCH, gmail.READ, brand="gmail"),
        service("calendar", calendar.EVENTS, calendar.CREATE, brand="google-calendar"),
        service("drive", drive.SEARCH, drive.READ, brand="google-drive"),
        service("contacts", contacts.SEARCH),
        service("tasks", tasks.LIST, tasks.ADD, tasks.COMPLETE, brand="google-tasks"),
    ),
)


class GoogleConnector(AccountConnector):
    name = "google"
    brand = "google"
    info = INFO
    feed = GmailInbound
    new_client = staticmethod(new_client)

    def __init__(self, *, poll_interval_s: float = 30.0, **settings: Any) -> None:
        super().__init__(poll_interval_s=poll_interval_s, **settings)

    async def identify(self, connection: Connection, access: Access) -> str:
        email = (await self._api(access).profile()).email
        if not email:
            raise ProviderError("gmail", "the profile has no email address", transient=False)
        return email

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        account, api = connection.account, lambda: self._api(access)
        return (
            *gmail.GmailTools(account, api, body_chars=self.body_chars).tools(),
            *calendar.CalendarTools(account, api).tools(),
            *drive.DriveTools(account, api, self.reader, body_chars=self.body_chars, max_bytes=self.file_bytes).tools(),
            *contacts.ContactTools(account, api, self.known(connection)).tools(),
            *tasks.TaskTools(account, api).tools(),
        )

    def _api(self, access: Access) -> GmailApi:
        return GmailApi(access, self.client)
