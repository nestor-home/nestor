"""Every resource checks its scope: what each role may open, and what it is refused."""

from pathlib import Path

import pytest

from nestor.modules.accounts import Role

from ...harness import Harness

OWNER, ADMIN, MEMBER, GUEST = Role.OWNER, Role.ADMIN, Role.MEMBER, Role.GUEST
EVERYONE = {OWNER, ADMIN, MEMBER, GUEST}
HOUSEHOLD = {OWNER, ADMIN, MEMBER}
MANAGERS = {OWNER, ADMIN}

ROUTES = [
    ("GET", "/api/v1/accounts", None, MANAGERS),
    ("GET", "/api/v1/invitations", None, MANAGERS),
    ("POST", "/api/v1/invitations", {"role": "guest", "person": "lucie"}, MANAGERS),
    ("POST", "/api/v1/invitations", {"role": "owner"}, {OWNER}),
    ("GET", "/api/v1/household/people", None, HOUSEHOLD),
    ("GET", "/api/v1/agent/activity", None, HOUSEHOLD),
    ("GET", "/api/v1/agent/initiative", None, HOUSEHOLD),
    ("GET", "/api/v1/connectors", None, HOUSEHOLD),
    ("PUT", "/api/v1/connectors/mailbox/client", {"client_id": "c", "client_secret": "s"}, MANAGERS),
    ("GET", "/api/v1/connections", None, HOUSEHOLD),
    ("GET", "/api/v1/satellites", None, MANAGERS),
    ("POST", "/api/v1/satellites/approvals", {"code": "123456"}, MANAGERS),
    ("GET", "/api/v1/journal", None, EVERYONE),
    ("GET", "/api/v1/journal/filters", None, EVERYONE),
    ("GET", "/api/v1/tasks", None, HOUSEHOLD),
    ("GET", "/api/v1/watches", None, HOUSEHOLD),
    ("GET", "/api/v1/memories", None, EVERYONE),
]


@pytest.mark.parametrize(("method", "path", "body", "allowed"), ROUTES, ids=[f"{m} {p}" for m, p, _, _ in ROUTES])
async def test_each_role_opens_what_it_may_and_is_refused_the_rest(
    tmp_path: Path, method: str, path: str, body: object, allowed: set[Role]
) -> None:
    async with Harness(tmp_path) as admin:
        for role, person in ((ADMIN, None), (MEMBER, "mathilde"), (GUEST, "lucie")):
            await admin.account(role.value, role, person)
        for role in (OWNER, ADMIN, MEMBER, GUEST):
            api = await admin.api("mathis" if role is OWNER else role.value)
            response = await api.send(method, path, body)
            if role in allowed:
                assert response.status_code != 403, (role, response.text)
            else:
                assert response.status_code == 403, role
                assert response.json()["error"]["code"] == "forbidden"


async def test_nothing_opens_without_signing_in(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        for method, path, body, _ in ROUTES:
            response = await api.send(method, path, body)
            assert response.status_code == 401 and response.json()["error"]["code"] == "unauthenticated", path


async def test_a_disabled_account_loses_its_open_sessions_at_once(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        member = await admin.account("mathilde", MEMBER, "mathilde")
        session = await admin.api("mathilde")
        owner = await admin.api()
        assert (await owner.post(f"/api/v1/accounts/{member.id}/disable")).json()["disabled"] is True
        assert (await session.get("/api/v1/journal")).status_code == 401
        assert (await session.sign_in("mathilde")).status_code == 401


async def test_a_role_change_applies_to_open_sessions_immediately(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        member = await admin.account("mathilde", MEMBER, "mathilde")
        session = await admin.api("mathilde")
        assert (await session.get("/api/v1/accounts")).status_code == 403
        owner = await admin.api()
        await owner.put(f"/api/v1/accounts/{member.id}/role", {"role": "admin"})
        assert (await session.get("/api/v1/accounts")).status_code == 200
