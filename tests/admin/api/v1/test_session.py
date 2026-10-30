"""Signing in to the API: credentials, throttling, the session cookie, CSRF on every change, revocation."""

from pathlib import Path

import pytest

from nestor.modules.accounts import AccountLogin, Role

from ...harness import OWNER, PASSWORD, Harness


async def test_signing_in_returns_who_is_signed_in_with_scopes_and_csrf_token(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        response = await api.sign_in("Mathis")
        me = response.json()
        assert response.status_code == 200
        assert me["account"]["login"] == "mathis" and me["account"]["role"] == "owner"
        assert me["account"]["role_label"] == "propriétaire" and me["account"]["person"] == {
            "id": "mathis",
            "name": "Mathis",
        }
        assert "accounts.owners.manage" in me["scopes"] and me["assistant"] == "Richie" and me["csrf_token"]
        assert (await api.get("/api/v1/me")).json() == me


async def test_a_member_is_told_only_its_own_scopes(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        scopes = (await (await admin.api("mathilde")).get("/api/v1/me")).json()["scopes"]
        assert "journal.read.own" in scopes and "journal.read.all" not in scopes and "accounts.manage" not in scopes


async def test_wrong_credentials_are_refused_with_a_uniform_error(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        for login, password in (("mathis", "not the password"), ("nobody", PASSWORD)):
            response = await api.sign_in(login, password)
            assert response.status_code == 401
            assert response.json() == {
                "error": {
                    "code": "invalid_credentials",
                    "message_id": "error-invalid-credentials",
                    "args": {},
                    "message": "Identifiant ou mot de passe incorrect.",
                }
            }
        assert (await api.get("/api/v1/me")).json()["error"]["code"] == "unauthenticated"
        attempts = await admin.nestor.journal.history(AccountLogin)
        assert [a.reason for a in attempts] == ["wrong-password", "unknown-login"]


async def test_guessing_is_throttled_even_for_the_right_password(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        for _ in range(5):
            assert (await api.sign_in(OWNER, "guess-guess")).status_code == 401
        response = await api.sign_in(OWNER)
        assert response.status_code == 429 and response.json()["error"]["code"] == "throttled"
        assert int(response.headers["retry-after"]) > 800
        assert (await api.get("/api/v1/me")).status_code == 401


async def test_the_session_cookie_is_http_only_and_strict_and_secure_over_https(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        cookie = (await (await admin.api(None)).sign_in(OWNER)).headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" not in cookie
    async with Harness(tmp_path / "https", public_url="https://nestor.example.org") as admin:
        assert "Secure" in (await (await admin.api(None)).sign_in(OWNER)).headers["set-cookie"]


async def test_signing_in_again_replaces_the_previous_session(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        before = dict(api.client.cookies)
        await api.sign_in(OWNER)
        assert dict(api.client.cookies) != before
        api.client.cookies.clear()
        api.client.cookies.update(before)
        assert (await api.get("/api/v1/me")).status_code == 401, "a session planted before signing in is worth nothing"


@pytest.mark.parametrize("header", [None, "forged"])
async def test_a_change_without_the_csrf_header_is_refused_and_changes_nothing(
    tmp_path: Path, header: str | None
) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        memory = await admin.nestor.memories.remember("Le code du portail est 1234")
        api.csrf = ""
        extra = {"X-CSRF-Token": header} if header else {}
        response = await api.send("DELETE", f"/api/v1/memories/{memory.id}", **extra)
        assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
        assert await admin.nestor.memories.store.get(memory.id) is not None
        signed_out = await api.send("DELETE", "/api/v1/session", **extra)
        assert signed_out.status_code == 403 and (await api.get("/api/v1/me")).status_code == 200


async def test_a_change_must_be_json_so_that_a_form_from_another_site_cannot_send_it(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        response = await api.client.post("/api/v1/session", data={"login": OWNER, "password": PASSWORD})
        assert response.status_code == 415 and response.json()["error"]["code"] == "unsupported_media_type"
        raw = await api.client.post(
            "/api/v1/session",
            content=f'{{"login": "{OWNER}", "password": "{PASSWORD}"}}',
            headers={"Content-Type": "text/plain"},
        )
        assert raw.status_code == 415 and "set-cookie" not in raw.headers


async def test_a_malformed_body_is_reported_with_its_fields(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        response = await (await admin.api(None)).post("/api/v1/session", {"login": OWNER, "extra": 1})
        error = response.json()["error"]
        assert response.status_code == 422 and error["code"] == "invalid_request" and "password" in error["message"]


async def test_signing_out_ends_this_session_for_good(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        stolen = dict(api.client.cookies)
        assert (await api.delete("/api/v1/session")).status_code == 204
        api.client.cookies.update(stolen)
        assert (await api.get("/api/v1/me")).status_code == 401


async def test_changing_ones_password_signs_out_every_other_session(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        laptop, phone = await admin.api(), await admin.api()
        wrong = await laptop.put("/api/v1/me/password", {"current_password": "nope", "new_password": "new password!"})
        assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "wrong_password"
        weak = await laptop.put("/api/v1/me/password", {"current_password": PASSWORD, "new_password": "short"})
        assert weak.status_code == 400 and weak.json()["error"]["code"] == "weak_password"
        assert (await phone.get("/api/v1/me")).status_code == 200

        changed = await laptop.put(
            "/api/v1/me/password", {"current_password": PASSWORD, "new_password": "new password!"}
        )
        assert changed.status_code == 204
        assert (await laptop.get("/api/v1/me")).status_code == 200
        assert (await phone.get("/api/v1/me")).status_code == 401
        assert (await phone.sign_in(OWNER)).status_code == 401
        assert (await phone.sign_in(OWNER, "new password!")).status_code == 200


async def test_an_unknown_api_address_answers_in_json(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        missing = await api.get("/api/v1/nowhere")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
        wrong_method = await api.send("PUT", "/api/v1/journal")
        assert wrong_method.status_code == 405 and wrong_method.json()["error"]["code"] == "method_not_allowed"
