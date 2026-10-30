"""What is plugged in, by family: brand, version, capabilities and health, satellites included."""

from importlib import metadata
from pathlib import Path

from nestor.core import Capability, Health
from nestor.modules.accounts import Role
from nestor.modules.channels import Medium
from nestor.modules.satellites import DeclaredCapability, Device, Manifest
from nestor.runtime import Distribution, Registry
from nestor.testing.channels import InMemoryChannel

from ...harness import Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon", brand="pollen-robotics"),
    (DeclaredCapability(Capability("audio.capture")),),
    sdk="nestor-reachy 0.1.0",
)


class Voice(InMemoryChannel):
    medium = Medium.SPOKEN
    brand = "webrtc"

    @property
    def rooms(self) -> frozenset[str]:
        return frozenset()

    def health(self) -> Health:
        return Health.DEGRADED

    def details(self) -> dict[str, str]:
        return {"speech": "elevenlabs"}


async def test_the_system_lists_every_plugged_component_and_paired_satellite(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        pairing = admin.nestor.pairing
        await pairing.approve((await pairing.request(REACHY)).code)
        api = await admin.api()
        system = (await api.get("/api/v1/system")).json()
        assert system["version"] == metadata.version("nestor-home")
        by_name = {(c["family"], c["name"]): c for c in system["components"]}
        assert {"model", "executor", "channel", "presence", "connector"} <= {f for f, _ in by_name}
        assert by_name[("channel", "telegram")]["health"] == "started"
        assert by_name[("connector", "mailbox")]["version"] is None, "registered by code, not by a package"
        satellite = by_name[("satellite", "reachy-salon")]
        assert satellite["brand"] == "pollen-robotics" and satellite["version"] == "nestor-reachy 0.1.0"
        assert satellite["kind"] == "reachy-mini" and satellite["health"] is None, "no spoken channel to tell"

        admin.nestor.channels.append(Voice("voice"))
        satellite = next(
            c for c in (await api.get("/api/v1/system")).json()["components"] if c["name"] == "reachy-salon"
        )
        assert satellite["health"] == "unavailable" and satellite["details"] == {"room": "salon"}


async def test_the_system_is_for_those_who_run_the_household(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        assert (await (await admin.api("mathilde")).get("/api/v1/system")).status_code == 403


def test_an_installed_plugin_knows_the_package_it_comes_from() -> None:
    from nestor.runtime import Family

    registry = Registry.installed()
    origin = registry.origin(Family.CHANNEL, "telegram")
    assert origin == Distribution("nestor-home", metadata.version("nestor-home"))
