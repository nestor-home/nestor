"""Editing the configuration: where its components and their secrets are found."""

from nestor.runtime.editing import ConfigSchema
from nestor.runtime.plugins import Registry

DOCUMENT = {
    "models": {
        "haiku": {
            "type": "language",
            "provider": "openai-compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-1",
            "model": "h",
        },
        "local": {
            "type": "language",
            "provider": "openai-compatible",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen3",
        },
    },
    "channels": [{"kind": "telegram", "name": "famille", "token": "1:a"}],
}


def test_a_named_models_secret_is_kept_under_its_name() -> None:
    found = ConfigSchema(Registry.installed()).secrets_of(DOCUMENT)
    assert found[("models", "haiku", "api_key")] == "models.haiku.api_key"
    assert found[("channels", 0, "token")] == "channels.famille.token"
    assert ("models", "local", "api_key") not in found, "a key left out is no secret to keep"


def test_a_plugins_settings_embedded_elsewhere_keep_their_words_and_a_choice_of_forms_is_named() -> None:
    """The home's actions server takes any MCP server's settings: their message ids stay the MCP plugin's."""
    home = ConfigSchema(Registry.installed()).slots()["home"]["kinds"]["home-assistant"]
    embedded = home["$defs"]["McpSettings"]["properties"]["include"]["x-nestor"]
    assert embedded["help_id"] == "config-tools-mcp-include-help"
    calls = home["$defs"]["SensitiveCalls"]["properties"]["tool"]["x-nestor"]
    assert calls["title_id"] == "config-tools-mcp-sensitivecalls-tool"
    forms = home["properties"]["mcp"]["x-nestor"]["variants"]
    assert [v["key"] for v in forms] == ["mcpsettings", "false", "default"]
    assert home["properties"]["url"]["x-nestor"]["variants"] is None, "a single form is no choice"
    found = ConfigSchema(Registry.installed()).secrets_of(
        {"home": {"kind": "home-assistant", "url": "http://ha", "token": "t", "mcp": {"url": "u", "token": "s"}}}
    )
    assert found[("home", "mcp", "token")] == "home.mcp.token", "the embedded server's token is a secret too"
