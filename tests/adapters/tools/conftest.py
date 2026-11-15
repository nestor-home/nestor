"""What the search engines' tests share: their APIs mocked, keys, and an API that refuses a key."""

from collections.abc import Iterator

import httpx
import pytest
import respx

KEY = "key-0123456789abcdef"
OTHER_KEY = "revoked-key-fedcba9876543210"


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def refusing(key: str) -> httpx.Response:
    """An API that refuses a key, quoting it."""
    return httpx.Response(401, json={"error": {"message": f"invalid key {key}"}})
