"""Editing the configuration: where its components and their secrets are found."""

from nestor.runtime.editing import ConfigSchema
from nestor.runtime.plugins import Registry

DOCUMENT = {
    "models": {
        "haiku": {
            "kind": "openai-compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-1",
            "model": "h",
        },
        "local": {"kind": "openai-compatible", "base_url": "http://localhost:11434/v1", "model": "qwen3"},
    },
    "channels": [{"kind": "telegram", "name": "famille", "token": "1:a"}],
}


def test_a_named_models_secret_is_kept_under_its_name() -> None:
    found = ConfigSchema(Registry.installed()).secrets_of(DOCUMENT)
    assert found[("models", "haiku", "api_key")] == "models.haiku.api_key"
    assert found[("channels", 0, "token")] == "channels.famille.token"
    assert ("models", "local", "api_key") not in found, "a key left out is no secret to keep"
