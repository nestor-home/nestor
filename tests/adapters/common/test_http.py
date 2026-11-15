"""The shared HTTP client: an error answer keeps its status, and how long the provider asked to wait."""

import email.utils
from datetime import timedelta

import httpx
import pytest

from nestor.adapters.common.http import HttpApi, StatusError
from nestor.core import utc_now


@pytest.mark.parametrize("as_date", [False, True], ids=["seconds", "date"])
async def test_a_refusal_keeps_its_status_and_the_wait_it_asks_for(as_date: bool) -> None:
    seconds = 600.0
    in_ten_minutes = email.utils.format_datetime(utc_now() + timedelta(seconds=seconds), usegmt=True)
    waited = in_ten_minutes if as_date else str(int(seconds))
    answer = httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"Retry-After": waited})
    api = HttpApi("api", "https://api.example", transport=httpx.MockTransport(lambda request: answer))
    with pytest.raises(StatusError) as refused:
        await api.request("GET", "/things")
    assert refused.value.status == 429 and refused.value.transient
    assert refused.value.retry_after_s == pytest.approx(seconds, abs=2)
