"""Settings of the remote MCP connector, and how it is built from them."""

from pydantic import PositiveFloat

from nestor.adapters.connectors.mcp.connector import McpConnector
from nestor.runtime import AdapterSettings, Services


class McpConnectorSettings(AdapterSettings):
    timeout_s: PositiveFloat = 10.0
    retry_after_s: PositiveFloat = 30.0


def build(settings: McpConnectorSettings, name: str, services: Services) -> McpConnector:
    connector = McpConnector(timeout_s=settings.timeout_s, retry_after_s=settings.retry_after_s)
    connector.name = name
    return connector
