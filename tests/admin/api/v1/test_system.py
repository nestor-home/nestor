"""What is plugged in, by family: brand, version, capabilities and health, satellites included."""

from importlib import metadata
from pathlib import Path

from nestor.core import Capability, Health
from nestor.modules.accounts import Role
from nestor.modules.channels import Medium
from nestor.modules.satellites import DeclaredCapability, Device, Manifest, Software
from nestor.modules.system import Releases
from nestor.runtime import Distribution, Registry
from nestor.testing.channels import InMemoryChannel
from nestor.testing.satellites import pair_by_code

from ...harness import Harness

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon", brand="pollen-robotics"),
    (DeclaredCapability(Capability("audio.capture")),),
    software=Software("nestor-reachy", "0.1.0"),
)


class Voice(InMemoryChannel):
    media = frozenset({Medium.SPOKEN})
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
        await pair_by_code(pairing, REACHY)
        api = await admin.api()
        system = (await api.get("/api/v1/system")).json()
        assert system["nestor"] == {"version": metadata.version("nestor-home")}
        by_name = {(c["slot"], c["name"]): c for c in system["components"]}
        assert {"model", "executor", "channel", "presence", "connector"} <= {f for f, _ in by_name}
        assert by_name[("channel", "telegram")]["health"] == "started"
        assert by_name[("connector", "mailbox")]["version"] is None, "registered by code, not by a package"
        satellite = by_name[("satellite", "reachy-salon")]
        assert satellite["brand"] == "pollen-robotics" and satellite["version"] == "0.1.0"
        assert satellite["distribution"] == "nestor-reachy" and satellite["adapter"] == "reachy-mini"
        assert satellite["health"] is None and satellite["health_detail"] is None, "no spoken channel to tell"

        admin.nestor.channels.append(Voice("voice"))
        satellite = next(
            c for c in (await api.get("/api/v1/system")).json()["components"] if c["name"] == "reachy-salon"
        )
        assert satellite["health"] == "unavailable" and satellite["details"] == {"room": "salon"}
        assert satellite["health_detail"] == "Aucune connexion active depuis la pièce « salon »."


async def test_the_system_is_for_those_who_run_the_household(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        assert (await (await admin.api("mathilde")).get("/api/v1/system")).status_code == 403


def test_an_installed_plugin_knows_the_package_it_comes_from() -> None:
    from nestor.runtime import Family

    registry = Registry.installed()
    origin = registry.origin(Family.CHANNEL, "telegram")
    assert origin == Distribution("nestor-home", metadata.version("nestor-home"))


class Down(InMemoryChannel):
    def health(self) -> Health:
        return Health.UNAVAILABLE


async def test_the_agent_is_online_until_its_model_or_a_channel_cannot_serve(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        assert (await api.get("/api/v1/me")).json()["agent"] == {"name": "Richie", "status": "online"}
        admin.nestor.channels.append(Down("broken"))
        assert (await api.get("/api/v1/me")).json()["agent"]["status"] == "degraded"
        assert (await api.get("/api/v1/system")).json()["agent"] == {"name": "Richie", "status": "degraded"}


def _feed(*versions: str, protocols: tuple[str, ...] = ("nestor.satellite/1",)) -> Releases:
    return Releases.from_json({
        "protocols": list(protocols),
        "releases": [
            {"version": v, "date": "2026-11-05", "url": f"https://x/v{v}",
             "changes": [{"kind": "breaking", "text": "models by role"}] if v == "9.0.0" else []}
            for v in versions
        ],
    })  # fmt: skip


async def test_the_admin_learns_what_was_released_since_the_running_version(tmp_path: Path) -> None:
    running = metadata.version("nestor-home")
    async with Harness(tmp_path) as admin:
        await pair_by_code(admin.nestor.pairing, REACHY)
        api = await admin.api()
        unknown = (await api.get("/api/v1/system/updates")).json()
        assert unknown["running"] == running and unknown["checking"] is True
        assert (unknown["latest"], unknown["checked_at"], unknown["releases"]) == (None, None, [])

        admin.releases.releases = _feed(running)
        assert admin.nestor.updates is not None
        await admin.nestor.updates.check()
        current = (await api.get("/api/v1/system/updates")).json()
        assert current["latest"] == running and current["releases"] == [] and current["checked_at"]

        admin.releases.releases = _feed("9.0.0", "8.0.0", running, protocols=("nestor.satellite/2",))
        await admin.nestor.updates.check()
        newer = (await api.get("/api/v1/system/updates")).json()
        assert [(r["version"], r["breaking"]) for r in newer["releases"]] == [("9.0.0", True), ("8.0.0", False)]
        assert newer["releases"][0]["changes"] == [{"kind": "breaking", "text": "models by role"}]
        assert newer["latest"] == "9.0.0" and newer["outdated_satellites"] == ["reachy-salon"]
        assert isinstance(newer["container"], bool)

        await admin.account("mathilde", Role.MEMBER, "mathilde")
        assert (await (await admin.api("mathilde")).get("/api/v1/system/updates")).status_code == 403


async def test_an_instance_told_not_to_check_says_so(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        admin.nestor.updates = None
        answer = (await (await admin.api()).get("/api/v1/system/updates")).json()
        assert (answer["checking"], answer["latest"], answer["releases"]) == (False, None, [])
