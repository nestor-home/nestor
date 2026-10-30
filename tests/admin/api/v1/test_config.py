"""Editing the configuration from the admin: forms from the schema, secrets kept in the vault, nothing
written that cannot be used, a history to go back to, and a restart only when a person asks."""

import asyncio
from pathlib import Path
from typing import Any

from nestor.modules.accounts import Role
from nestor.modules.system import ConfigChanged, RestartRequested, SecretChanged

from ...harness import Api, Harness

KEY = "wk-0123456789abcdef"


def weather(**settings: Any) -> dict[str, Any]:
    return {"kind": "weather", "api_key": {"value": KEY}, "city": "${WEATHER_CITY}", **settings}


async def document(api: Api) -> dict[str, Any]:
    response = await api.get("/api/v1/config")
    assert response.status_code == 200, response.text
    return response.json()["document"]


async def test_the_schema_gives_every_section_and_every_installed_plugin_its_form(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        schema = (await (await admin.api()).get("/api/v1/config/schema")).json()
        assert {"persona", "household", "initiative", "admin", "data_dir"} <= set(schema["sections"])
        assert schema["section_titles"]["household"] == "Foyer"
        locale = schema["sections"]["persona"]["properties"]["locale"]["x-nestor"]
        assert locale["title"] == "Langue" and locale["help"].startswith("La langue du foyer")
        assert locale["title_id"] == "config-persona-locale" and locale["group"] == "persona"
        slots = schema["slots"]
        assert slots["channels"]["many"] and slots["channels"]["required"] and slots["channels"]["title"] == "Canaux"
        tool = slots["tools"]["kinds"]["weather"]
        properties = tool["properties"]
        assert properties["kind"]["const"] == "weather" and "kind" in tool["required"]
        assert properties["api_key"]["x-nestor"]["secret"] and not properties["city"]["x-nestor"]["secret"]
        assert properties["retries"]["x-nestor"]["advanced"]
        assert properties["name"]["x-nestor"]["title"] == "Nom", "a field no catalogue names gets the generic title"
        assert properties["city"]["x-nestor"]["title"] == "City", "or its own name"
        token, headers = properties["token"]["x-nestor"], properties["headers"]["x-nestor"]
        assert token["secret"] and not token["secret_values"], "an optional secret is a secret"
        assert headers["secret_values"] and not headers["secret"], "a map of secrets is masked value by value"
        nested = tool["$defs"]["WeatherAccount"]["properties"]["password"]["x-nestor"]
        assert nested["secret"], "nested settings are annotated too"
        assert tool["$defs"]["Units"]["enum"] == ["metric", "imperial"]


async def test_a_typed_secret_goes_to_the_vault_and_the_file_keeps_a_reference(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        edited = await document(api)
        edited["tools"] = [weather()]
        edited["persona"]["name"] = "Nestor"
        written = await api.put("/api/v1/config", {"document": edited})
        assert written.status_code == 200, written.text
        diff = written.json()["diff"]
        assert {"path": "persona.name", "before": "Richie", "after": "Nestor", "secret": False} in diff["changed"]
        assert {"path": "tools.0.api_key", "before": None, "after": None, "secret": True} in diff["added"]
        text = admin.config_path.read_text()
        assert "${secret:tools.weather.api_key}" in text and KEY not in text
        assert "city: ${WEATHER_CITY}" in text, "references stay references"
        assert text.startswith("# The test household's assistant"), "comments survive"
        secrets = admin.app.state.admin.secrets
        assert await secrets.value("tools.weather.api_key") == KEY

        shown = await document(api)
        assert shown["tools"][0]["api_key"] == "${secret:tools.weather.api_key}"
        (changed,) = await admin.nestor.journal.history(ConfigChanged)
        assert admin.owner and changed.by == admin.owner.id and "persona.name" in changed.changed_paths
        (secret,) = await admin.nestor.journal.history(SecretChanged)
        assert secret.name == "tools.weather.api_key"
        me = (await api.get("/api/v1/me")).json()
        system = (await api.get("/api/v1/system")).json()
        assert me["restart_required"] and system["restart_required"]
        assert "persona.name" in system["pending_changes"]
        assert not any(KEY in seen for seen in admin.seen), "a secret never comes back"


async def test_a_literal_secret_is_masked_and_a_blank_field_keeps_it(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        admin.config_path.write_text(
            admin.config_path.read_text() + f"tools: [{{kind: weather, api_key: {KEY}, city: Lyon}}]\n"
        )
        api = await admin.api()
        shown = await document(api)
        assert shown["tools"][0]["api_key"] == {"set": True, "preview": "wk-…def"}
        shown["tools"][0]["city"] = "Paris"
        assert (await api.put("/api/v1/config", {"document": shown})).status_code == 200
        assert KEY in admin.config_path.read_text(), "echoing {set, preview} keeps the value where it is"
        shown = await document(api)
        shown["tools"][0]["api_key"] = {"value": ""}
        assert (await api.put("/api/v1/config", {"document": shown})).status_code == 200
        assert KEY in admin.config_path.read_text(), "a blank field keeps it too"
        shown = await document(api)
        shown["tools"][0]["api_key"] = "wk-typed-in-a-plain-field"
        await api.put("/api/v1/config", {"document": shown})
        assert "wk-typed" not in admin.config_path.read_text(), "a value typed as text goes to the vault as well"


async def test_a_configuration_that_cannot_be_used_is_not_written_and_says_where(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        before = admin.config_path.read_text()
        edited = await document(api)
        del edited["persona"]["name"]
        edited["tools"] = [{"kind": "weather", "api_key": "${secret:nowhere}", "city": "${UNSET_VARIABLE}"}]
        refused = await api.put("/api/v1/config", {"document": edited})
        assert refused.status_code == 422
        error = refused.json()["error"]
        assert error["code"] == "config_invalid"
        assert {(tuple(p["path"]), p["code"]) for p in error["problems"]} == {
            (("tools", 0, "api_key"), "secret"),
            (("tools", 0, "city"), "reference"),
        }, "references are checked first"
        edited["tools"] = [{"kind": "weather", "api_key": {"value": KEY}}, {"kind": "teleporter"}]
        problems = (await api.put("/api/v1/config", {"document": edited})).json()["error"]["problems"]
        assert {(tuple(p["path"]), p["code"]) for p in problems} == {(("persona", "name"), "missing")}
        edited["persona"]["name"] = "Richie"
        problems = (await api.put("/api/v1/config", {"document": edited})).json()["error"]["problems"]
        assert {(tuple(p["path"]), p["code"]) for p in problems} == {
            (("tools", 0, "city"), "missing"),
            (("tools", 1, "kind"), "unknown_kind"),
        }
        message = next(p for p in problems if p["code"] == "unknown_kind")
        assert message["message"] == "tools.1.kind : aucun greffon « teleporter » n'est installé."
        assert admin.config_path.read_text() == before
        assert await admin.app.state.admin.secrets.value("tools.weather.api_key") is None, "nor any secret"


async def test_a_preview_says_what_would_change_without_writing(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        before = admin.config_path.read_text()
        edited = await document(api)
        edited["initiative"] = {"quiet_hours": "22:30-07:30"}
        edited["tools"] = [weather()]
        preview = (await api.post("/api/v1/config/preview", {"document": edited})).json()
        assert preview["valid"] and preview["problems"] == []
        assert {"path": "initiative.quiet_hours", "before": None, "after": "22:30-07:30", "secret": False} in (
            preview["diff"]["added"]
        )
        assert admin.config_path.read_text() == before
        edited["initiative"] = {"quiet_hours": "late"}
        refused = (await api.post("/api/v1/config/preview", {"document": edited})).json()
        assert not refused["valid"] and refused["problems"][0]["path"] == ["initiative", "quiet_hours"]


async def test_an_earlier_configuration_can_be_read_and_restored(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        original = admin.config_path.read_text()
        edited = await document(api)
        edited["persona"]["name"] = "Nestor"
        await api.put("/api/v1/config", {"document": edited})
        (entry,) = (await api.get("/api/v1/config/history")).json()
        earlier = (await api.get(f"/api/v1/config/history/{entry['id']}")).json()
        assert earlier["document"]["persona"]["name"] == "Richie"
        restored = await api.post(f"/api/v1/config/history/{entry['id']}/restore")
        assert restored.status_code == 200 and admin.config_path.read_text() == original
        assert len((await api.get("/api/v1/config/history")).json()) == 2, "restoring keeps what it replaces"
        assert (await admin.nestor.journal.history(ConfigChanged))[-1].restored == entry["id"]
        assert (await api.get("/api/v1/config/history/nope")).status_code == 404
        assert (await api.post("/api/v1/config/history/nope/restore")).status_code == 404


async def test_secrets_are_listed_with_their_use_set_write_only_and_kept_while_used(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        edited = await document(api)
        edited["tools"] = [weather()]
        await api.put("/api/v1/config", {"document": edited})
        set_ = await api.put("/api/v1/config/secrets/spare", {"value": "sk-abcdefghijkl"})
        assert set_.json() == {"name": "spare", "set": True, "preview": "sk-…jkl", "used_by": []}
        listed = {s["name"]: s for s in (await api.get("/api/v1/config/secrets")).json()}
        assert listed["tools.weather.api_key"]["used_by"] == ["tools.0.api_key"]
        assert set(listed) == {"tools.weather.api_key", "spare"}
        in_use = await api.delete("/api/v1/config/secrets/tools.weather.api_key")
        assert in_use.status_code == 409 and "tools.0.api_key" in in_use.json()["error"]["message"]
        assert (await api.delete("/api/v1/config/secrets/tools.weather.api_key?force=true")).status_code == 204
        assert (await api.get("/api/v1/config/secrets/tools.weather.api_key")).json()["set"] is False
        assert (await api.delete("/api/v1/config/secrets/spare")).status_code == 204
        assert (await api.delete("/api/v1/config/secrets/spare")).status_code == 404
        assert not any("sk-abcdefghijkl" in seen or KEY in seen for seen in admin.seen)


async def test_only_owners_and_admins_edit_the_configuration(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        member = await admin.api("mathilde")
        for path in ("/api/v1/config", "/api/v1/config/schema", "/api/v1/config/secrets", "/api/v1/config/history"):
            assert (await member.get(path)).status_code == 403, path


async def test_a_restart_is_asked_for_by_a_person_and_confirmed(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        restarted = asyncio.Event()
        admin.app.state.admin.restart = restarted.set
        api = await admin.api()
        unconfirmed = await api.post("/api/v1/system/restart", {"confirm": False})
        assert unconfirmed.status_code == 400 and not restarted.is_set()
        accepted = await api.post("/api/v1/system/restart", {"confirm": True})
        assert accepted.status_code == 202 and accepted.json() == {"restarting": True}
        await asyncio.wait_for(restarted.wait(), 2)
        (requested,) = await admin.nestor.journal.history(RestartRequested)
        assert admin.owner and requested.by == admin.owner.id
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        member = await admin.api("mathilde")
        assert (await member.post("/api/v1/system/restart", {"confirm": True})).status_code == 403


async def test_without_a_file_or_a_key_there_is_nothing_to_edit(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        state = admin.app.state.admin
        state.editor, state.secrets = None, None
        api = await admin.api()
        assert (await api.get("/api/v1/config")).json()["error"]["code"] == "config_unavailable"
        assert (await api.get("/api/v1/config/secrets")).json()["error"]["code"] == "no_secret_key"


async def test_secret_headers_are_masked_kept_replaced_and_removed_key_by_key(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        admin.config_path.write_text(
            admin.config_path.read_text()
            + "tools:\n  - kind: weather\n    api_key: ${secret:spare}\n    city: Lyon\n"
            + "    token: tk-literal-token-1234\n"
            + "    headers: {Authorization: Bearer hdr-literal-0001, X-Gone: gone-literal-0002}\n"
        )
        api = await admin.api()
        await api.put("/api/v1/config/secrets/spare", {"value": KEY})
        shown = await document(api)
        tool = shown["tools"][0]
        assert tool["token"] == {"set": True, "preview": "tk-…234"}
        assert tool["headers"] == {
            "Authorization": {"set": True, "preview": "Bea…001"},
            "X-Gone": {"set": True, "preview": "gon…002"},
        }

        tool["headers"] = {
            "Authorization": tool["headers"]["Authorization"],  # echoed: kept as it is
            "X-Api-Key": {"value": "hk-typed-in-the-form"},  # new
        }
        preview = (await api.post("/api/v1/config/preview", {"document": shown})).json()
        assert preview["valid"], preview["problems"]
        diff = preview["diff"]
        assert {"path": "tools.0.headers.X-Api-Key", "before": None, "after": None, "secret": True} in diff["added"]
        assert {"path": "tools.0.headers.X-Gone", "before": None, "after": None, "secret": True} in diff["removed"]
        assert all(c["path"] != "tools.0.headers.Authorization" for c in diff["changed"]), "an echo changes nothing"

        assert (await api.put("/api/v1/config", {"document": shown})).status_code == 200
        text = admin.config_path.read_text()
        assert "Bearer hdr-literal-0001" in text and "tk-literal-token-1234" in text, "what was echoed stays"
        assert "gone-literal-0002" not in text and "X-Gone" not in text
        assert "${secret:tools.weather.headers.X-Api-Key}" in text and "hk-typed" not in text
        secrets = admin.app.state.admin.secrets
        assert await secrets.value("tools.weather.headers.X-Api-Key") == "hk-typed-in-the-form"

        shown = await document(api)
        assert shown["tools"][0]["headers"]["X-Api-Key"] == "${secret:tools.weather.headers.X-Api-Key}"
        shown["tools"][0]["headers"]["Authorization"] = {"value": "Bearer hdr-replaced-0003"}
        shown["tools"][0]["token"] = {"value": ""}  # blank: kept
        written = (await api.put("/api/v1/config", {"document": shown})).json()
        changed = {c["path"]: c for c in written["diff"]["changed"]}
        assert changed["tools.0.headers.Authorization"] == {
            "path": "tools.0.headers.Authorization",
            "before": None,
            "after": None,
            "secret": True,
        }
        assert await secrets.value("tools.weather.headers.Authorization") == "Bearer hdr-replaced-0003"
        text = admin.config_path.read_text()
        assert "hdr-literal" not in text and "hdr-replaced" not in text and "tk-literal-token-1234" in text
        assert not any(v in seen for seen in admin.seen for v in ("hdr-", "hk-typed", "tk-literal"))
