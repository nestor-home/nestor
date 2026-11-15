"""The executors and their keys for Nestor's MCP server, from the admin: made and shown once, renewed, revoked."""

from pathlib import Path

from nestor.modules.accounts import Role
from nestor.modules.cognition.delegation import ExecutorKeyIssued, ExecutorKeyRevoked

from ....harness import Harness


async def test_a_key_is_shown_once_works_until_renewed_or_revoked(tmp_path: Path) -> None:
    async with Harness(tmp_path, public_url="https://nestor.example") as admin:
        api, keys = await admin.api(), admin.nestor.executor_keys
        assert keys is not None
        name = admin.nestor.executors[0].name
        listed = (await api.get("/api/v1/executors")).json()
        assert listed["url"] == "https://nestor.example/mcp"
        assert [(e["name"], e["nestor_tools"], e["key"]) for e in listed["executors"]] == [(name, "none", None)]

        first = (await api.post(f"/api/v1/executors/{name}/key")).json()
        assert first["key"].startswith("nstx_") and first["url"] == "https://nestor.example/mcp"
        assert keys.caller(first["key"]) == name
        [executor] = (await api.get("/api/v1/executors")).json()["executors"]
        assert executor["key"]["issued_at"] and executor["key"]["last_used_at"] is None
        assert first["key"] not in (await api.get("/api/v1/executors")).text, "never shown again"

        second = (await api.post(f"/api/v1/executors/{name}/key")).json()
        assert keys.caller(first["key"]) is None and keys.caller(second["key"]) == name, "renewed: the old one ends"
        assert (await api.delete(f"/api/v1/executors/{name}/key")).status_code == 204
        assert keys.caller(second["key"]) is None
        assert (await api.get("/api/v1/executors")).json()["executors"][0]["key"] is None
        issued = await admin.nestor.journal.history(ExecutorKeyIssued, ExecutorKeyRevoked)

    assert [type(e).__name__ for e in issued] == ["ExecutorKeyIssued", "ExecutorKeyIssued", "ExecutorKeyRevoked"]
    assert all(e.by is not None for e in issued) and first["key"] not in str([e.to_record() for e in issued])


async def test_without_a_public_address_no_key_is_made(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api, name = await admin.api(), admin.nestor.executors[0].name
        assert (await api.get("/api/v1/executors")).json()["url"] is None
        refused = await api.post(f"/api/v1/executors/{name}/key")
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "executors_unreachable"


async def test_only_who_manages_the_configuration_makes_keys_and_only_for_an_executor_it_has(tmp_path: Path) -> None:
    async with Harness(tmp_path, public_url="https://nestor.example") as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        member, name = await admin.api("mathilde"), admin.nestor.executors[0].name
        assert (await member.post(f"/api/v1/executors/{name}/key")).status_code == 403
        assert (await member.delete(f"/api/v1/executors/{name}/key")).status_code == 403
        unknown = await (await admin.api()).post("/api/v1/executors/codex/key")
        assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "executor_unknown"
