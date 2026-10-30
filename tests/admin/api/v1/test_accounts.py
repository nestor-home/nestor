"""Accounts through the API: invitations end to end, roles, the last owner, resets — and no secret leaks."""

import urllib.parse
from datetime import timedelta
from pathlib import Path

from nestor.modules.accounts import Role

from ...harness import OWNER, PASSWORD, Harness


def token_of(url: str) -> str:
    fragment = urllib.parse.urlsplit(url).fragment
    return dict(urllib.parse.parse_qsl(fragment))["token"]


async def test_an_invited_person_opens_their_account_and_is_signed_in(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        owner = await admin.api()
        created = await owner.post("/api/v1/invitations", {"role": "member", "person": "mathilde"})
        assert created.status_code == 201
        body = created.json()
        assert body["url"].startswith("http://admin.test/invitation#token=")
        assert body["invitation"]["status"] == "pending" and body["invitation"]["person"]["name"] == "Mathilde"
        token = token_of(body["url"])
        assert token == body["token"]
        listed = (await owner.get("/api/v1/invitations")).json()
        assert [i["id"] for i in listed] == [body["invitation"]["id"]] and token not in str(listed)

        guest = await admin.api(None)
        preview = (await guest.post("/api/v1/invitations/inspect", {"token": token})).json()
        assert preview["role_label"] == "membre" and preview["person"]["id"] == "mathilde"
        weak = await guest.post("/api/v1/invitations/accept", {"token": token, "login": "mathilde", "password": "x"})
        assert weak.json()["error"]["code"] == "weak_password"
        bad = await guest.post(
            "/api/v1/invitations/accept", {"token": token, "login": "Ma thilde", "password": PASSWORD}
        )
        assert bad.json()["error"]["code"] == "invalid_login"
        taken = await guest.post("/api/v1/invitations/accept", {"token": token, "login": OWNER, "password": PASSWORD})
        assert taken.status_code == 409

        accepted = await guest.post(
            "/api/v1/invitations/accept", {"token": token, "login": "mathilde@free.fr", "password": PASSWORD}
        )
        assert accepted.status_code == 201 and accepted.json()["account"]["role"] == "member"
        assert (await guest.get("/api/v1/me")).json()["account"]["login"] == "mathilde@free.fr"
        again = await (await admin.api(None)).post(
            "/api/v1/invitations/accept", {"token": token, "login": "other", "password": PASSWORD}
        )
        assert again.status_code == 400 and again.json()["error"] == {
            "code": "invitation_refused",
            "message": "Cette invitation a déjà servi.",
        }
        assert (await owner.get("/api/v1/invitations")).json()[0]["status"] == "accepted"


async def test_an_expired_or_withdrawn_invitation_is_refused(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        owner = await admin.api()
        expiring = token_of(
            (await owner.post("/api/v1/invitations", {"role": "guest", "person": "lucie"})).json()["url"]
        )
        later = admin.nestor.accounts.now() + timedelta(hours=49)
        admin.nestor.accounts._clock = lambda: later
        guest = await admin.api(None)
        expired = await guest.post("/api/v1/invitations/inspect", {"token": expiring})
        assert expired.json()["error"]["message"] == "Cette invitation a expiré : demandez-en une nouvelle."
        assert (await owner.get("/api/v1/invitations")).json()[0]["status"] == "expired"

        withdrawn = (await owner.post("/api/v1/invitations", {"role": "guest", "person": "lucie"})).json()
        assert (await owner.delete(f"/api/v1/invitations/{withdrawn['invitation']['id']}")).status_code == 204
        refused = await guest.post("/api/v1/invitations/inspect", {"token": withdrawn["token"]})
        assert refused.json()["error"]["message"] == "Cette invitation a été retirée."
        unknown = await guest.post("/api/v1/invitations/inspect", {"token": "nothing"})
        assert unknown.json()["error"]["message"] == "Cette invitation est inconnue."
        assert (await owner.delete("/api/v1/invitations/nope")).status_code == 404


async def test_an_invitation_names_a_person_of_the_household_for_members_and_guests(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        owner = await admin.api()
        stranger = await owner.post("/api/v1/invitations", {"role": "guest", "person": "stranger"})
        assert stranger.json()["error"]["code"] == "unknown_person"
        nobody = await owner.post("/api/v1/invitations", {"role": "member"})
        assert nobody.json()["error"]["code"] == "person_required"
        twice = await owner.post("/api/v1/invitations", {"role": "member", "person": "mathis"})
        assert twice.status_code == 409 and twice.json()["error"]["code"] == "conflict"
        technical = await owner.post("/api/v1/invitations", {"role": "admin"})
        assert technical.status_code == 201 and technical.json()["invitation"]["person"] is None


async def test_the_last_owner_stays_an_owner(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        owner = await admin.api()
        assert admin.owner
        demoted = await owner.put(f"/api/v1/accounts/{admin.owner.id}/role", {"role": "admin"})
        assert demoted.status_code == 409 and demoted.json()["error"]["code"] == "last_owner"
        disabled = await owner.post(f"/api/v1/accounts/{admin.owner.id}/disable")
        assert disabled.status_code == 409
        second = await admin.account("lucie", Role.OWNER, "lucie")
        assert (await owner.put(f"/api/v1/accounts/{second.id}/role", {"role": "member"})).json()["role"] == "member"


async def test_an_admin_manages_members_but_never_owners(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("lucie", Role.ADMIN, "lucie")
        member = await admin.account("mathilde", Role.MEMBER, "mathilde")
        api = await admin.api("lucie")
        assert admin.owner
        for method, path, body in (
            ("PUT", f"/api/v1/accounts/{admin.owner.id}/role", {"role": "member"}),
            ("POST", f"/api/v1/accounts/{admin.owner.id}/disable", None),
            ("PUT", f"/api/v1/accounts/{admin.owner.id}/password", {"password": "taken over!!"}),
            ("PUT", f"/api/v1/accounts/{member.id}/role", {"role": "owner"}),
        ):
            assert (await api.send(method, path, body)).status_code == 403, path
        assert (await api.post(f"/api/v1/accounts/{member.id}/disable")).json()["disabled"] is True
        assert (await api.post(f"/api/v1/accounts/{member.id}/enable")).json()["disabled"] is False
        listed = (await api.get("/api/v1/accounts")).json()
        assert [a["login"] for a in listed] == ["mathis", "lucie", "mathilde"]


async def test_resetting_someones_password_signs_them_out(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        member = await admin.account("mathilde", Role.MEMBER, "mathilde")
        theirs, owner = await admin.api("mathilde"), await admin.api()
        weak = await owner.put(f"/api/v1/accounts/{member.id}/password", {"password": "short"})
        assert weak.status_code == 400
        assert (
            await owner.put(f"/api/v1/accounts/{member.id}/password", {"password": "a fresh password"})
        ).status_code == 204
        assert (await theirs.get("/api/v1/me")).status_code == 401
        assert (await theirs.sign_in("mathilde", "a fresh password")).status_code == 200
        assert admin.owner
        own = await owner.put(f"/api/v1/accounts/{admin.owner.id}/password", {"password": "a fresh password"})
        assert own.json()["error"]["code"] == "use_me_password"
        assert (await owner.put("/api/v1/accounts/nope/role", {"role": "guest"})).status_code == 404


async def test_no_response_ever_holds_a_password_or_its_hash(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        owner = await admin.api()
        invited = (await owner.post("/api/v1/invitations", {"role": "member", "person": "mathilde"})).json()
        guest = await admin.api(None)
        await guest.post(
            "/api/v1/invitations/accept", {"token": invited["token"], "login": "mathilde", "password": PASSWORD}
        )
        for path in (
            "/api/v1/accounts",
            "/api/v1/invitations",
            "/api/v1/me",
            "/api/v1/journal",
            "/api/v1/household/people",
        ):
            await owner.get(path)
        secret = invited["token"].split(".", 1)[1]
        creation = [i for i, seen in enumerate(admin.seen) if secret in seen]
        assert len(creation) == 1, "the invitation token is shown once, when it is created"
        for seen in admin.seen:
            assert PASSWORD not in seen and "scrypt$" not in seen
