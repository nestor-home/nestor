"""Admin plumbing: settings that cannot work are refused, guessing ages out, sessions expire and are revoked."""

import pytest

from nestor.admin import AdminSettings
from nestor.admin.auth import LoginThrottle, SessionStore
from nestor.core import ContractError


def test_settings_refuse_urls_that_cannot_work() -> None:
    with pytest.raises(ContractError, match="public_url must be an http"):
        AdminSettings(public_url="nestor.local")
    with pytest.raises(ContractError, match="relay_url must be served over HTTPS"):
        AdminSettings(relay_url="http://relay.example/oauth")


def test_failures_age_out_of_the_throttle() -> None:
    now = [0.0]
    throttle = LoginThrottle(failures=2, window_s=60, clock=lambda: now[0])
    throttle.failed("1.2.3.4")
    throttle.failed("1.2.3.4")
    assert throttle.wait_s("1.2.3.4") == 60 and throttle.wait_s("5.6.7.8") == 0
    now[0] = 61
    assert throttle.wait_s("1.2.3.4") == 0
    throttle.failed("1.2.3.4")
    throttle.succeeded("1.2.3.4")
    assert throttle.wait_s("1.2.3.4") == 0


def test_sessions_expire_and_the_oldest_goes_when_full() -> None:
    now = [0.0]
    store = SessionStore(ttl_s=10, limit=2, clock=lambda: now[0])
    oldest, kept = store.open("a"), store.open("b")
    newest = store.open("c")  # over the limit: the oldest goes
    assert store.find(store.cookie(oldest)) is None
    assert store.find(store.cookie(kept)) is kept and store.find(store.cookie(newest)) is newest
    assert store.find(None) is None
    now[0] = 11
    assert store.find(store.cookie(kept)) is None
    fresh = store.open("d")  # expired sessions are dropped first
    assert store.find(store.cookie(fresh)) is fresh


def test_a_forged_cookie_is_no_session() -> None:
    store = SessionStore(ttl_s=10)
    session = store.open("a")
    assert store.find(f"{session.id}.0000") is None and store.find(store.cookie(session)) is session


def test_revoking_an_account_closes_its_sessions_but_the_kept_one() -> None:
    store = SessionStore(ttl_s=10)
    kept, other, someone_else = store.open("a"), store.open("a"), store.open("b")
    assert store.revoke("a", keep=kept) == 1
    assert store.alive(kept) and not store.alive(other) and store.alive(someone_else)
    assert store.find(store.cookie(other)) is None
