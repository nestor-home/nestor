"""Configuration of an MCP tool provider, as written under `tools:` in the Nestor configuration, or as the server of a
home's actions (`home.mcp`). Its words are the same wherever it is embedded (`messages`)."""

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, SecretStr

from nestor.adapters.tools.mcp.provider import BearerToken, McpToolProvider, McpTransport, Negotiation
from nestor.modules.cognition.tools import Risk, SensitiveWhen
from nestor.runtime import AdapterSettings, Services


class SensitiveCalls(BaseModel):
    """Calls confirmed by the person first when one of these values appears in an argument: a server's tools may
    drive harmless and dangerous things alike."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra={"messages": "tools-mcp-sensitivecalls"})
    tool: str | None = None  # its name on the server (`delete_issue`); none: every tool that acts
    arguments: dict[str, list[str]]  # `{device_class: [garage, gate], domain: [lock], name: [porte]}`

    def rule(self) -> SensitiveWhen:
        return SensitiveWhen(self.tool, {key: tuple(values) for key, values in self.arguments.items()})


class McpSettings(AdapterSettings):
    model_config = ConfigDict(json_schema_extra={"messages": "tools-mcp"})
    url: str
    transport: McpTransport = McpTransport.STREAMABLE_HTTP
    token: SecretStr | None = None  # sent as `Authorization: Bearer …`
    headers: dict[str, SecretStr] = Field(default_factory=dict)  # values may be credentials: kept secret
    timeout_s: PositiveFloat = 10.0  # connecting, and each tool call
    include: list[str] | None = None  # server tool names offered to the agent; all when unset
    exclude: list[str] = Field(default_factory=list)
    risks: dict[str, Risk] = Field(default_factory=dict)  # by server tool name, over the annotations
    sensitive: list[SensitiveCalls] = Field(default_factory=list)  # calls confirmed first, by what they act on
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
        sensitive=[calls.rule() for calls in settings.sensitive],
        retry_after_s=settings.retry_after_s,
        negotiation=settings.negotiation,
    )
