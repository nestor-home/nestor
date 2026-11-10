"""The home as the admin shows it: who is where, its rooms and residents, how the household is tied to it, and its
actions with the ones that need a go-ahead."""

from pathlib import Path

from nestor.modules.accounts import Role
from nestor.modules.satellites import Device, Manifest
from nestor.testing.satellites import SOFTWARE, pair_by_code

from ....harness import Harness


async def test_the_home_shows_its_rooms_residents_ties_and_actions(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await pair_by_code(admin.nestor.pairing, Manifest(Device("mic", "esp32", "SALON"), software=SOFTWARE))
        home = (await (await admin.api()).get("/api/v1/home")).json()
        offered = {spec.name for spec in admin.nestor.toolbox.specs()}
    assert {"lights", "unlock"} <= offered, "the home's actions are the agent's tools"

    assert (home["connected"], home["granularity"], home["component"]["health"]) == (True, "home", "started")
    assert home["rooms"] == [
        {
            "id": "salon",
            "name": "Salon",
            "occupied": True,
            "people": [{"id": "mathis", "name": "Mathis"}],
            "satellites": ["mic"],  # its room named as the home names it, case aside
        },
        {"id": "cuisine", "name": "Cuisine", "occupied": None, "people": [], "satellites": []},
    ]
    assert home["residents"] == [
        {"entity": "person.mathis", "name": "Mathis", "home": True, "person": {"id": "mathis", "name": "Mathis"}},
        {"entity": "person.mathilde", "name": "Mathilde", "home": None, "person": None},
    ], "a resident tied to nobody says so"
    tied = {p["person"]["id"]: (p["entity"], p["presence"]["home"]) for p in home["people"]}
    assert tied == {"mathis": ("person.mathis", True), "mathilde": (None, None), "lucie": (None, None)}
    assert [(t["name"], t["risk"]) for t in home["tools"]] == [("lights", "write"), ("unlock", "sensitive")]


async def test_without_a_home_system_the_home_is_null_and_a_guest_does_not_see_it(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("lucie", Role.GUEST, "lucie")
        assert (await (await admin.api("lucie")).get("/api/v1/home")).status_code == 403
    async with Harness(tmp_path / "bare", home=False) as bare:
        response = await (await bare.api()).get("/api/v1/home")
    assert (response.status_code, response.json()) == (200, None)
