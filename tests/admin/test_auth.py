"""Only the household gets in: password, session cookie, CSRF on every form, throttled guessing."""

from pathlib import Path

import pytest

from nestor.admin import AdminSettings, hash_password, verify_password
from nestor.admin.auth import LoginThrottle, SessionStore
from nestor.core import ContractError

from .harness import Harness

PAGES = ["/", "/journal", "/connections", "/connectors/mailbox", "/tasks", "/watches", "/memories", "/people"]
FORMS = [
    "/logout",
    "/connectors/mailbox/client",
    "/connectors/mailbox/connect",
    "/connections/abc/tools",
    "/connections/abc/disconnect",
    "/tasks/abc/cancel",
    "/watches/abc/cancel",
    "/memories/abc/correct",
    "/memories/abc/forget",
]


async def test_no_page_is_reachable_without_logging_in(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for path in PAGES:
            response = await admin.get(path)
            if path == "/":
                response = await admin.get(response.headers["location"])
            assert response.status_code == 303, path
            assert response.headers["location"].startswith("/login"), path
        for path in FORMS:
            response = await admin.post(path, {"text": "x"})
            assert (response.status_code, response.headers["location"]) == (303, "/login"), path
        callback = await admin.get("/connections/callback", state="s", code="c")
        assert callback.headers["location"].startswith("/login?next=%2Fconnections%2Fcallback")


async def test_health_static_files_and_the_login_page_are_public(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        assert (await admin.get("/health")).json() == {"status": "ok"}
        assert "--accent" in (await admin.get("/static/admin.css")).text
        login = await admin.get("/login")
        assert login.status_code == 200 and "Mot de passe" in login.text


async def test_the_household_password_opens_the_requested_page(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.get("/login", next="/memories")
        response = await admin.post("/login", {"password": "correct horse battery", "next": "/memories"})
        assert (response.status_code, response.headers["location"]) == (303, "/memories")
        page = await admin.get("/memories")
        assert page.status_code == 200 and "Souvenirs" in page.text
        assert (await admin.get("/login")).headers["location"] == "/"


async def test_a_wrong_password_is_refused(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        response = await admin.login("not the password")
        assert response.status_code == 401 and "Mot de passe incorrect" in response.text
        assert (await admin.get("/journal")).status_code == 303


async def test_guessing_is_throttled_even_for_the_right_password(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for _ in range(5):
            assert (await admin.login("guess")).status_code == 401
        response = await admin.login()
        assert response.status_code == 429 and "Réessayez dans 15 min" in response.text
        assert (await admin.get("/journal")).status_code == 303


async def test_the_login_form_needs_the_token_of_its_page(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.get("/login")
        response = await admin.post("/login", {"password": "correct horse battery", "csrf": "forged"})
        assert response.status_code == 403
        admin.browser.cookies.clear()
        assert (await admin.post("/login", {"password": "correct horse battery"}, csrf=False)).status_code == 403


async def test_a_form_without_its_csrf_token_changes_nothing(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        memory = await admin.nestor.memories.remember("Le code du portail est 1234")
        for data in ({"csrf": "forged"}, {}):
            response = await admin.browser.post(f"/memories/{memory.id}/forget", data=data)
            assert response.status_code == 403 and "Formulaire refusé" in response.text
        assert await admin.nestor.memories.store.get(memory.id) is not None


async def test_the_session_cookie_is_http_only_lax_and_renewed_at_login(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        anonymous = (await admin.get("/login")).headers["set-cookie"]
        response = await admin.post("/login", {"password": "correct horse battery"})
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" not in cookie
        assert cookie.split(";")[0] != anonymous.split(";")[0], "a session id planted before login is worth nothing"


async def test_the_cookie_is_secure_when_the_admin_is_served_over_https(tmp_path: Path) -> None:
    async with Harness(tmp_path, public_url="https://nestor.example.org") as admin:
        await admin.get("/login")
        response = await admin.post("/login", {"password": "correct horse battery"})
        assert "Secure" in response.headers["set-cookie"]


async def test_logging_out_ends_the_session_for_good(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        stolen = dict(admin.browser.cookies)
        assert (await admin.post("/logout")).headers["location"] == "/login"
        admin.browser.cookies.update(stolen)
        assert (await admin.get("/journal")).status_code == 303


async def test_a_forged_cookie_is_not_a_session(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.login()
        (name, value), *_ = admin.browser.cookies.items()
        session_id, _, _ = value.partition(".")
        admin.browser.cookies.clear()
        admin.browser.cookies.set(name, f"{session_id}.0000")
        assert (await admin.get("/journal")).status_code == 303


@pytest.mark.parametrize("target", ["//evil.example/", "https://evil.example/", "/\\evil.example"])
async def test_logging_in_never_redirects_off_site(tmp_path: Path, target: str) -> None:
    async with Harness(tmp_path) as admin:
        await admin.get("/login")
        response = await admin.post("/login", {"password": "correct horse battery", "next": target})
        assert response.headers["location"] == "/"


async def test_pages_forbid_framing_and_referrers(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        headers = (await admin.get("/login")).headers
        assert headers["x-frame-options"] == "DENY" and headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["cache-control"] == "no-store"


def test_a_password_hash_verifies_only_its_password() -> None:
    encoded = hash_password("correct horse battery")
    assert encoded.startswith("scrypt$") and "correct" not in encoded
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("correct horse batterY", encoded)
    assert encoded != hash_password("correct horse battery"), "salted"


def test_a_short_password_or_a_malformed_hash_is_refused() -> None:
    with pytest.raises(ContractError, match="at least 10"):
        hash_password("short")
    for broken in ("plain-password", "scrypt$x$8$1$AA==$AA==", "bcrypt$1$2$3$AA==$AA=="):
        with pytest.raises(ContractError, match="nestor admin-password"):
            AdminSettings(password_hash=broken)


def test_settings_refuse_urls_that_cannot_work() -> None:
    encoded = hash_password("correct horse battery")
    with pytest.raises(ContractError, match="public_url must be an http"):
        AdminSettings(password_hash=encoded, public_url="nestor.local")
    with pytest.raises(ContractError, match="relay_url must be served over HTTPS"):
        AdminSettings(password_hash=encoded, relay_url="http://relay.example/oauth")


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


def test_sessions_expire_and_anonymous_ones_are_evicted_first() -> None:
    now = [0.0]
    store = SessionStore(ttl_s=10, limit=2, clock=lambda: now[0])
    logged_in = store.open(authenticated=True)
    store.open()
    store.open()  # over the limit: the anonymous one goes, not the household's
    assert store.find(store.cookie(logged_in)) is logged_in
    assert store.find(None) is None
    now[0] = 11
    assert store.find(store.cookie(logged_in)) is None
    fresh = store.open()  # expired sessions are dropped first
    assert store.find(store.cookie(fresh)) is fresh
