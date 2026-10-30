"""Connectors: third-party services plugged in from the admin — Gmail, IMAP mailboxes, MCP servers.

A connector declares how it is authorised and what it brings (tools, inbound items for watches); a
connection is one account plugged into it, owned by a person. Tokens live in an encrypted vault and
never reach the model or the journal.
"""

from nestor.modules.connectors.assistant import ConnectorTools
from nestor.modules.connectors.events import ConnectionChanged, ConnectionCreated, ConnectionRemoved
from nestor.modules.connectors.inbound import ConnectedInbound
from nestor.modules.connectors.ports import Access, Connector, CredentialVault, TokenEndpoint
from nestor.modules.connectors.service import Connections
from nestor.modules.connectors.types import (
    AuthKind,
    Connection,
    ConnectorInfo,
    OAuthSpec,
    SecretField,
    Secrets,
    Status,
    Tokens,
)

__all__ = [
    "Access",
    "AuthKind",
    "ConnectedInbound",
    "Connection",
    "ConnectionChanged",
    "ConnectionCreated",
    "ConnectionRemoved",
    "Connections",
    "Connector",
    "ConnectorInfo",
    "ConnectorTools",
    "CredentialVault",
    "OAuthSpec",
    "SecretField",
    "Secrets",
    "Status",
    "TokenEndpoint",
    "Tokens",
]
