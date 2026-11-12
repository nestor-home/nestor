"""`find_place` and `route` over Nominatim and OSRM, mocked with the shapes they answer: journeys from home by the
mode asked, and Nominatim's usage policy of one search a second."""

import time
from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.tools.openstreetmap import NOMINATIM, ROUTING, OpenStreetMap
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext, ToolFailed

CONTEXT = ToolContext(address=Address("web", "chat"))
PLACES = {
    "12 rue Mercière, Lyon": {"lat": "45.7620", "lon": "4.8330", "name": "", "display_name": "12, Rue Mercière, Lyon"},
    "New York": {"lat": "40.7127", "lon": "-74.0060", "name": "New York", "display_name": "New York, United States"},
    "Gare Part-Dieu": {
        "lat": "45.7606",
        "lon": "4.8594",
        "name": "Gare de Lyon Part-Dieu",
        "type": "station",
        "display_name": "Gare de Lyon Part-Dieu, Lyon",
    },
}


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{NOMINATIM}/search").mock(
            side_effect=lambda r: httpx.Response(200, json=[PLACES[q]] if (q := r.url.params["q"]) in PLACES else [])
        )
        router.get(url__regex=rf"{ROUTING}/routed-bike/route/v1/driving/4\.8330,45\.7620;4\.8594,45\.7606").respond(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 2712.4,
                        "duration": 1003.0,
                        "legs": [{"summary": "Rue de la République, Cours Lafayette"}],
                    }
                ],
            },
        )
        router.get(url__regex=rf"{ROUTING}/routed-foot/.*").respond(400, json={"code": "NoRoute", "routes": []})
        # a server covers a region: a place outside it is moved to its nearest road, thousands of km away
        router.get(url__regex=rf"{ROUTING}/routed-car/.*-74\.0060.*").respond(
            200,
            json={
                "code": "Ok",
                "routes": [{"distance": 1742902.2, "duration": 66514.0, "legs": [{"summary": ""}]}],
                "waypoints": [
                    {"location": [4.8330, 45.7620], "distance": 3.2},
                    {"location": [-9.4977, 38.7807], "distance": 5534234.2},
                ],
            },
        )
        yield router


async def call(name: str, home: str | None = "12 rue Mercière, Lyon", **arguments: object) -> dict:
    async with OpenStreetMap(home=home, language="fr-FR") as maps:
        tool = next(t for t in maps.tools() if t.name == name)
        output = await tool.run(arguments, CONTEXT)
    assert isinstance(output, dict)
    return output


async def test_a_journey_starts_from_home_by_the_mode_asked_with_searches_a_second_apart(
    api: respx.MockRouter,
) -> None:
    searched: list[float] = []
    api.routes[0].side_effect = lambda r, s=api.routes[0].side_effect: (searched.append(time.monotonic()), s(r))[1]
    journey = await call("route", destination="Gare Part-Dieu", mode="bike")
    assert journey == {
        "from": "12, Rue Mercière, Lyon",
        "to": "Gare de Lyon Part-Dieu, Lyon",
        "mode": "bike",
        "distance_km": 2.7,
        "duration_min": 17,
        "via": "Rue de la République, Cours Lafayette",
    }
    assert searched[1] - searched[0] >= 1.0, "Nominatim's usage policy: one search a second at most"


@pytest.mark.parametrize(
    ("home", "arguments", "says"),
    [
        ("12 rue Mercière, Lyon", {"destination": "Atlantide"}, "Atlantide"),
        (None, {"destination": "Gare Part-Dieu"}, "ask where from"),
        ("12 rue Mercière, Lyon", {"destination": "Gare Part-Dieu", "mode": "foot"}, "no foot route"),
        ("12 rue Mercière, Lyon", {"destination": "Gare Part-Dieu", "mode": "plane"}, "mode is one of"),
        ("12 rue Mercière, Lyon", {"destination": "New York"}, "no road near New York"),
    ],
    ids=["unknown-place", "no-start-no-home", "no-route", "unknown-mode", "out-of-the-server-s-region"],
)
async def test_a_journey_that_cannot_be_computed_fails_the_tool(home: str | None, arguments: dict, says: str) -> None:
    with pytest.raises(ToolFailed, match=says):
        await call("route", home, **arguments)


async def test_places_are_found_with_their_address_and_coordinates() -> None:
    found = await call("find_place", query="Gare Part-Dieu")
    assert found["places"] == [
        {
            "name": "Gare de Lyon Part-Dieu",
            "address": "Gare de Lyon Part-Dieu, Lyon",
            "kind": "station",
            "latitude": 45.7606,
            "longitude": 4.8594,
        }
    ]
