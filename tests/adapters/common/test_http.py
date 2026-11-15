"""The shared HTTP client: an error answer keeps its status, and how long the provider asked to wait."""

import email.utils
from datetime import timedelta

import httpx
import pytest

from nestor.adapters.common.http import HttpApi, StatusError
from nestor.core import utc_now


@pytest.mark.parametrize(
    ("waited", "seconds"),
    [("120", 120.0), (email.utils.format_datetime(utc_now() + timedelta(minutes=10), usegmt=True), 600.0)],
    ids=["seconds", "date"],
)
async def test_a_refusal_keeps_its_status_and_the_wait_it_asks_for(waited: str, seconds: float) -> None:
    answer = httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"Retry-After": waited})
    api = HttpApi("api", "https://api.example", transport=httpx.MockTransport(lambda request: answer))
    with pytest.raises(StatusError) as refused:
        await api.request("GET", "/things")
    assert refused.value.status == 429 and refused.value.transient
    assert refused.value.retry_after_s == pytest.approx(seconds, abs=2)
