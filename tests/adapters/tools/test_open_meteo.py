"""`weather` over Open-Meteo's geocoding and forecast APIs, mocked with the shapes they answer."""

from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.tools.open_meteo import OpenMeteo
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext, ToolFailed

CONTEXT = ToolContext(address=Address("web", "chat"))
GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
PLACES = {
    "Lyon": {
        "name": "Lyon",
        "latitude": 45.75,
        "longitude": 4.85,
        "admin1": "Auvergne-Rhône-Alpes",
        "country": "France",
    },
    "Brest": {"name": "Brest", "latitude": 48.39, "longitude": -4.49, "admin1": "Bretagne", "country": "France"},
}
HOURS = [f"2026-11-12T{h:02d}:00" for h in range(24)] + [f"2026-11-13T{h:02d}:00" for h in range(24)]


def forecast(request: httpx.Request) -> httpx.Response:
    days = int(request.url.params["forecast_days"])
    rainy = float(request.url.params["longitude"]) < 0  # Brest
    return httpx.Response(
        200,
        json={
            "latitude": float(request.url.params["latitude"]),
            "current": {
                "time": "2026-11-12T14:15",
                "temperature_2m": 12.4,
                "apparent_temperature": 10.0,
                "relative_humidity_2m": 80,
                "precipitation": 0.2,
                "weather_code": 61 if rainy else 0,
                "wind_speed_10m": 17.6,
            },
            "hourly": {
                "time": HOURS,
                "temperature_2m": [10.0 + h % 24 / 4 for h in range(48)],
                "precipitation_probability": [90] * 48,
                "precipitation": [0.5] * 48,
                "weather_code": [61] * 48,
            },
            "daily": {
                "time": ["2026-11-12", "2026-11-13", "2026-11-14"][:days],
                "weather_code": [61, 3, 95][:days],
                "temperature_2m_max": [14.7, 13.0, 11.2][:days],
                "temperature_2m_min": [9.1, 8.0, 6.5][:days],
                "precipitation_sum": [18.7, 0.0, 30.1][:days],
                "precipitation_probability_max": [100, 10, 95][:days],
                "wind_speed_10m_max": [22.5, 12.0, 60.3][:days],
                "sunrise": ["2026-11-12T07:36"] * days,
                "sunset": ["2026-11-12T17:12"] * days,
            },
        },
    )


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(GEOCODING).mock(
            side_effect=lambda r: httpx.Response(
                200, json={"results": [PLACES[r.url.params["name"]]]} if r.url.params["name"] in PLACES else {}
            )
        )
        router.get(FORECAST).mock(side_effect=forecast)
        yield router


async def weather(home: str | None = "Lyon", **arguments: object) -> dict:
    async with OpenMeteo(home=home, language="fr-FR") as provider:
        [tool] = provider.tools()
        output = await tool.run(arguments, CONTEXT)
    assert isinstance(output, dict)
    return output


async def test_the_weather_at_home_now_over_the_next_hours_and_for_the_days_asked(api: respx.MockRouter) -> None:
    found = await weather(days=2)
    assert api.routes[0].calls.last.request.url.params["language"] == "fr"
    assert found["place"] == "Lyon, Auvergne-Rhône-Alpes, France"
    assert found["now"]["sky"] == "clear sky"
    assert [h["time"] for h in found["next_hours"]] == [f"2026-11-12T{h}:00" for h in (14, 17, 20, 23)] + [
        f"2026-11-13T{h:02d}:00" for h in (2, 5, 8, 11)
    ]
    assert [(d["date"], d["sky"], d["max"]) for d in found["days"]] == [
        ("2026-11-12", "light rain", 14.7),
        ("2026-11-13", "overcast", 13.0),
    ]


async def test_a_place_asked_is_found_by_name() -> None:
    found = await weather(place="Brest")
    assert (found["place"], found["now"]["sky"]) == ("Brest, Bretagne, France", "light rain")


@pytest.mark.parametrize(
    ("home", "arguments", "says"),
    [("Lyon", {"place": "Atlantide"}, "Atlantide"), (None, {}, "ask where")],
    ids=["unknown-place", "no-place-no-home"],
)
async def test_a_place_that_cannot_be_found_fails_the_tool(home: str | None, arguments: dict, says: str) -> None:
    with pytest.raises(ToolFailed, match=says):
        await weather(home, **arguments)


async def test_an_unreachable_service_fails_the_tool(api: respx.MockRouter) -> None:
    api.routes[1].side_effect = httpx.ConnectError("down")
    with pytest.raises(ToolFailed, match="could not be read"):
        await weather()
