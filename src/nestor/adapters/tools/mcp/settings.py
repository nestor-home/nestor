"""Configuration of an MCP tool provider, as written under `tools:` in the Nestor configuration."""

from pydantic import Field, PositiveFloat, PositiveInt, SecretStr

from nestor.adapters.tools.mcp.provider import BearerToken, McpToolProvider, McpTransport, Negotiation
from nestor.modules.cognition.tools import Risk
from nestor.runtime import AdapterSettings, Services


class McpSettings(AdapterSettings):
    url: str  # Home Assistant: https://<host>:8123/api/mcp
    transport: McpTransport = McpTransport.STREAMABLE_HTTP
    token: SecretStr | None = None  # sent as `Authorization: Bearer …`
    headers: dict[str, SecretStr] = Field(default_factory=dict)  # values may be credentials: kept secret
    timeout_s: PositiveFloat = 10.0  # connecting, and each tool call
    include: list[str] | None = None  # server tool names offered to the agent; all when unset
    exclude: list[str] = Field(default_factory=list)
    risks: dict[str, Risk] = Field(default_factory=dict)  # by server tool name, over the annotations
    max_result_chars: PositiveInt = 16_000
    retry_after_s: PositiveFloat = 30.0  # least delay between two reconnection attempts
    negotiation: Negotiation = "auto"  # `legacy` skips the 2026-07-28 discovery probe


def build(settings: McpSettings, name: str, services: Services) -> McpToolProvider:
    return McpToolProvider(
        settings.url,
        name=name,
        transport=settings.transport,
        auth=None if settings.token is None else BearerToken(settings.token.get_secret_value()),
        headers={key: value.get_secret_value() for key, value in settings.headers.items()},
        timeout_s=settings.timeout_s,
        include=settings.include,
        exclude=settings.exclude,
        risks=settings.risks,
        max_result_chars=settings.max_result_chars,
        retry_after_s=settings.retry_after_s,
        negotiation=settings.negotiation,
    )
