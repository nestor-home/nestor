"""What changing a connection takes; connections themselves are shared shapes (`ConnectionOut`)."""

from nestor.admin.api.v1.shared import Input


class ConnectionSettingsIn(Input):
    disabled_tools: list[str] | None = None
    confirm_writes: bool | None = None
