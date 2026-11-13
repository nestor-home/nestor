"""The Microsoft 365 connector: Outlook mail (read only, and new mail for watches) and calendar, OneDrive (read only)
and To Do of each connected account, work or personal, through Microsoft Graph."""

from collections.abc import Sequence

from nestor.adapters.connectors.common.accounts import AccountConnector
from nestor.adapters.connectors.common.tools import service
from nestor.adapters.connectors.microsoft import calendar, mail, onedrive, todo
from nestor.adapters.connectors.microsoft.graph import GraphApi, new_client
from nestor.adapters.connectors.microsoft.inbound import OutlookInbound
from nestor.core import ProviderError
from nestor.core.i18n import Message
from nestor.modules.cognition.tools import Tool
from nestor.modules.connectors import Access, AuthKind, Connection, ConnectorInfo, OAuthSpec

LOGIN = "https://login.microsoftonline.com/common/oauth2/v2.0"  # work, school and personal accounts alike
SCOPES = (
    "openid",
    "email",
    "offline_access",  # without it, no refresh token
    "User.Read",
    "Mail.Read",
    "MailboxSettings.Read",  # the time zone a whole day starts in
    "Calendars.ReadWrite",
    "Files.Read",
    "Tasks.ReadWrite",
)


INFO = ConnectorInfo(
    kind="microsoft",
    brand="microsoft",
    title=Message.of("connector-microsoft-title"),
    description=Message.of("connector-microsoft-description"),
    auth=AuthKind.OAUTH2,
    oauth=OAuthSpec(
        authorize_url=f"{LOGIN}/authorize",
        token_url=f"{LOGIN}/token",
        scopes=SCOPES,
        client_credentials=True,
    ),
    setup=Message.of("connector-microsoft-setup"),
    inbound=("mail",),
    services=(
        service("outlook", mail.SEARCH, mail.READ),
        service("calendar", calendar.EVENTS, calendar.CREATE),
        service("onedrive", onedrive.SEARCH, onedrive.READ),
        service("todo", todo.LIST, todo.ADD, todo.COMPLETE),
    ),
)


class MicrosoftConnector(AccountConnector):
    name = "microsoft"
    brand = "microsoft"
    info = INFO
    feed = OutlookInbound
    new_client = staticmethod(new_client)

    async def identify(self, connection: Connection, access: Access) -> str:
        me = await self._api(access).get("/me", [("$select", "mail,userPrincipalName")])
        account = str(me.get("mail") or me.get("userPrincipalName") or "")
        if not account:
            raise ProviderError("microsoft", "the profile has no address", transient=False)
        return account

    def tools(self, connection: Connection, access: Access) -> Sequence[Tool]:
        account, api, known = connection.account, lambda: self._api(access), self.known(connection)
        return (
            *mail.MailTools(account, api, body_chars=self.body_chars).tools(),
            *calendar.CalendarTools(account, api, known).tools(),
            *onedrive.DriveTools(
                account, api, self.reader, body_chars=self.body_chars, max_bytes=self.file_bytes
            ).tools(),
            *todo.TodoTools(account, api, known).tools(),
        )

    def _api(self, access: Access) -> GraphApi:
        return GraphApi(access, self.client)
