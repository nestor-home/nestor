"""Every resource checks its scope: what each role may open, and what it is refused."""

import json
import re
from pathlib import Path

import pytest

from nestor.admin import openapi_text
from nestor.core import Capability
from nestor.modules.accounts import Role
from nestor.modules.satellites import DeclaredCapability, Device, Manifest
from nestor.testing.satellites import SOFTWARE, pair_by_code

from ...harness import Harness

OWNER, ADMIN, MEMBER, GUEST = Role.OWNER, Role.ADMIN, Role.MEMBER, Role.GUEST
EVERYONE = {OWNER, ADMIN, MEMBER, GUEST}
HOUSEHOLD = {OWNER, ADMIN, MEMBER}
MANAGERS = {OWNER, ADMIN}
MIC = Manifest(
    Device("mic", "esp32", "bureau"),
    (DeclaredCapability(Capability("audio.capture")), DeclaredCapability(Capability("device.update"))),
    software=SOFTWARE,
)

# Each route, who may open it, and what they get: its success, or the answer of a request the handler itself
# turns down (a refusal past the scope check), never a 404 or 422 a route that is not there would give.
ROUTES: list[tuple[str, str, object, set[Role], int | tuple[int, str]]] = [
    ("GET", "/api/v1/accounts", None, MANAGERS, 200),
    ("GET", "/api/v1/accounts/{owner}", None, MANAGERS, 200),
    ("GET", "/api/v1/invitations", None, MANAGERS, 200),
    ("POST", "/api/v1/invitations", {"role": "admin"}, MANAGERS, 201),
    ("POST", "/api/v1/invitations", {"role": "owner"}, {OWNER}, 201),
    ("GET", "/api/v1/household/people", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/household/people/mathis", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/agent/activity", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/agent/initiative", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/connectors", None, HOUSEHOLD, 200),
    ("PUT", "/api/v1/connectors/mailbox/client", {"client_id": "c", "client_secret": "s"}, MANAGERS, 200),
    ("GET", "/api/v1/connections", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/satellites", None, MANAGERS, 200),
    ("GET", "/api/v1/satellites/mic", None, MANAGERS, 200),
    ("POST", "/api/v1/satellites/mic/update", {}, MANAGERS, (409, "satellite_offline")),
    ("POST", "/api/v1/satellites/approvals", {"code": "123456"}, MANAGERS, (400, "pairing_refused")),
    ("GET", "/api/v1/journal", None, EVERYONE, 200),
    ("GET", "/api/v1/journal/facets", None, EVERYONE, 200),
    ("GET", "/api/v1/tasks", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/watches", None, HOUSEHOLD, 200),
    ("GET", "/api/v1/memories", None, EVERYONE, 200),
    ("GET", "/api/v1/config", None, MANAGERS, 200),
    ("GET", "/api/v1/config/schema", None, MANAGERS, 200),
    ("GET", "/api/v1/config/secrets", None, MANAGERS, 200),
    ("GET", "/api/v1/config/history", None, MANAGERS, 200),
    ("POST", "/api/v1/system/restart", {"confirm": True}, MANAGERS, 202),
    ("GET", "/api/v1/system", None, MANAGERS, 200),
    ("GET", "/api/v1/system/updates", None, MANAGERS, 200),
    (
        "POST",
        "/api/v1/system/updates/install",
        {"version": "9.0.0", "confirm": True},
        MANAGERS,
        (409, "update_not_installable"),
    ),
]

# What a visitor reaches before signing in: signing in, an invitation, the catalogues to read the page.
OPEN = {
    ("post", "/api/v1/session"),
    ("post", "/api/v1/invitations/inspect"),
    ("post", "/api/v1/invitations/accept"),
    ("get", "/api/v1/i18n"),
    ("get", "/api/v1/i18n/{locale}"),
}


@pytest.mark.parametrize(
    ("method", "path", "body", "allowed", "expected"), ROUTES, ids=[f"{r[0]} {r[1]}" for r in ROUTES]
)
async def test_each_role_opens_what_it_may_and_is_refused_the_rest(
    tmp_path: Path, method: str, path: str, body: object, allowed: set[Role], expected: int | tuple[int, str]
) -> None:
    status, code = expected if isinstance(expected, tuple) else (expected, None)
    async with Harness(tmp_path) as admin:
        assert admin.owner
        admin.nestor.restart.stop = lambda: None
        await pair_by_code(admin.nestor.pairing, MIC)
        for role, person in ((ADMIN, None), (MEMBER, "mathilde"), (GUEST, "lucie")):
            await admin.account(role.value, role, person)
        for role in (OWNER, ADMIN, MEMBER, GUEST):
            api = await admin.api("mathis" if role is OWNER else role.value)
            response = await api.send(method, path.format(owner=admin.owner.id), body)
            if role in allowed:
                assert response.status_code == status, (role, response.text)
                assert code is None or response.json()["error"]["code"] == code, (role, response.text)
            else:
                assert response.status_code == 403, role
                assert response.json()["error"]["code"] == "forbidden"


async def test_nothing_opens_without_signing_in(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        for path, operations in json.loads(openapi_text())["paths"].items():
            for method in operations:
                if (method, path) in OPEN:
                    continue
                address = re.sub(r"\{position\}", "1", re.sub(r"\{phrase\}", "0", path))
                response = await api.send(method.upper(), re.sub(r"\{\w+\}", "x", address), {})
                assert response.status_code == 401, (method, path, response.status_code)
                assert response.json()["error"]["code"] == "unauthenticated", (method, path)


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
