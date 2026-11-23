"""What the model adapters share: which servers are the household's own, whose calls cost nothing."""

import pytest

from nestor.adapters.models.common import on_premises

SERVERS = [
    ("http://localhost:11434/v1", True),
    ("http://192.168.1.20:8080/v1", True),
    ("http://richie.local:8080/v1", True),
    ("http://host.docker.internal:1234/v1", True),
    ("http://pi:8080/v1", True),
    ("http://100.101.1.2:11434/v1", True),  # a machine of the household's Tailscale network
    ("http://box.tailnet-1234.ts.net:11434/v1", True),
    ("https://openrouter.ai/api/v1", False),
    ("https://api.groq.com/openai/v1", False),
    ("http://100.128.0.1/v1", False),  # just past Tailscale's addresses
]


@pytest.mark.parametrize(("base_url", "own"), SERVERS, ids=[s[0] for s in SERVERS])
def test_a_server_of_the_household_s_own_is_told_from_a_hosted_one(base_url: str, own: bool) -> None:
    assert on_premises(base_url) is own
