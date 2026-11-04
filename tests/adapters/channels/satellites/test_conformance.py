"""The black-box conformance suite, proven on the reference driver and on broken ones."""

import json
import sys

import pytest

from nestor.adapters.channels.satellites.conformance import Launch, check_satellite
from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.core import Capability
from nestor.modules.satellites import Device, Manifest, PairingMethod
from nestor.modules.satellites.types import DeclaredCapability
from nestor.testing.satellites import SOFTWARE, Finding

from .reference import Faults, ReferenceSatellite

MANIFEST = Manifest(
    Device("enceinte-cuisine", "raspberry-pi-4", "cuisine"),
    tuple(
        DeclaredCapability(Capability(name))
        for name in (
            "audio.capture",
            "audio.playback",
            "expression.emotion",
            "motion.head",
            "vision.person_detection",
            "device.identify",
            "device.update",
            "text.display",
        )
    ),
    (PairingMethod.DISPLAY, PairingMethod.PROVISIONING),
    software=SOFTWARE,
)


SPEAKER = Manifest(
    Device("enceinte-salon", "raspberry-pi-zero", "salon"),
    (DeclaredCapability(Capability("audio.capture")), DeclaredCapability(Capability("audio.playback"))),
    software=SOFTWARE,
)
SENSOR = Manifest(Device("capteur-entree", "esp32", "entree"),
                  (DeclaredCapability(Capability("vision.person_detection")),), software=SOFTWARE)  # fmt: skip
ENGLISH = FluentLocalizer(catalogue_dirs(["nestor"]))


def named(findings: list[Finding]) -> set[str]:
    """The checks, as an English reader sees them."""
    return {ENGLISH.format(f.check, "en") for f in findings}


async def test_the_reference_satellite_conforms() -> None:
    driver = ReferenceSatellite("", MANIFEST)
    findings = await check_satellite(driver, deadline_s=10)
    assert findings.passed, findings.failures()
    checks = named(findings.items)
    assert {
        "claims its token once its device code is typed (P2)",
        "opens its link with its token, a hello first, as the paired device (L1)",
        "receives the core's audio (A1, A2)",
        "sends its microphone audio (A1, A2)",
        "acknowledges intent.text within 1 s",
        "forgets a refused token and pairs again (L2, P8)",
        "offers no audio when audio is not allowed (A1)",
        "keeps polling after a pending identify (I1)",
        "acknowledges intent.expression within 1 s",
        "acknowledges intent.identify within 1 s",
        "acknowledges intent.update within 1 s",
        "reports where its software stands (U1)",
        "never installs a version it did not report (U2)",
        "enrolled: reports where its software stands (U1)",
        "reconnects with the same token after the core closes its link (L5)",
        "pairs with the enrollment code of NESTOR_PAIRING_URI, no code typed (P3, P4)",
        "presents a refused enrollment code (used) only once (P5)",
        "falls back to a device code after its enrollment code is refused (wrong) (P5)",
        "waits for Retry-After when rate-limited (P6)",
    } <= checks
    assert driver.identified >= 2  # once pending, once paired


@pytest.mark.parametrize("manifest", [SPEAKER, SENSOR], ids=["speaker without a body", "sensor without audio"])
async def test_a_device_is_only_checked_on_what_it_declared(manifest: Manifest) -> None:
    findings = await check_satellite(ReferenceSatellite("", manifest), deadline_s=10)
    assert findings.passed, findings.failures()
    checks = named(findings.items)
    assert "acknowledges intent.expression within 1 s" not in checks
    assert not {"acknowledges intent.identify within 1 s", "keeps polling after a pending identify (I1)"} & checks
    assert "reports where its software stands (U1)" not in checks
    assert ("receives the core's audio (A1, A2)" in checks) is (manifest is SPEAKER)


async def test_a_driver_can_be_any_program() -> None:
    command = [sys.executable, "-m", "tests.adapters.channels.satellites.reference", "{url}", "{state}",
               json.dumps(SPEAKER.to_json())]  # fmt: skip
    findings = await check_satellite(command, deadline_s=15)
    assert "pairs with the enrollment code of NESTOR_PAIRING_URI, no code typed (P3, P4)" in named(findings.items)
    assert findings.passed, findings.failures()


async def test_a_driver_program_that_exits_is_reported() -> None:
    findings = await check_satellite([sys.executable, "-c", "pass"], deadline_s=1)
    assert named(findings.failures()) == {"asks to pair", "runs without crashing"}


@pytest.mark.parametrize(
    ("faults", "failing"),
    [
        (Faults(acks=False), "acknowledges intent.behavior within 1 s"),
        (Faults(says_hello=False), "opens its link with its token, a hello first, as the paired device (L1)"),
        (Faults(claims_token=False), "claims its token once its device code is typed (P2)"),
        (Faults(connects=False), "runs without crashing"),
        (Faults(honest_hello=False), "opens its link with its token, a hello first, as the paired device (L1)"),
        (Faults(valid_messages=False), "every message follows the schema"),
        (Faults(reconnects=False), "reconnects with the same token after the core closes its link (L5)"),
        (Faults(forgets_refused_token=False), "forgets a refused token and pairs again (L2, P8)"),
        (Faults(offers_unallowed_audio=True), "offers no audio when audio is not allowed (A1)"),
        (Faults(reads_uri=False), "pairs with the enrollment code of NESTOR_PAIRING_URI, no code typed (P3, P4)"),
        (Faults(falls_back=False), "falls back to a device code after its enrollment code is refused (wrong) (P5)"),
        (Faults(retries_refused=True), "presents a refused enrollment code (expired) only once (P5)"),
        (Faults(honours_retry_after=False), "waits for Retry-After when rate-limited (P6)"),
        (Faults(reports_update=False), "reports where its software stands (U1)"),
        (Faults(installs_unreported=True), "never installs a version it did not report (U2)"),
    ],
    ids=[
        "no acks",
        "no hello",
        "never claims",
        "crashes",
        "someone else's hello",
        "off-contract message",
        "no reconnection",
        "keeps a refused token",
        "offers audio unallowed",
        "ignores its pairing URI",
        "stuck on a refused code",
        "insists on a refused code",
        "ignores Retry-After",
        "silent about its software",
        "installs what it is told",
    ],
)
async def test_a_broken_satellite_is_caught(faults: Faults, failing: str) -> None:
    findings = await check_satellite(ReferenceSatellite("", MANIFEST, faults=faults), deadline_s=3)
    assert failing in named(findings.failures())


async def test_an_observation_without_its_capability_is_off_contract() -> None:
    blind = Manifest(
        MANIFEST.device,
        tuple(c for c in MANIFEST.capabilities if c.name != "vision.person_detection"),
        software=SOFTWARE,
    )
    findings = await check_satellite(ReferenceSatellite("", blind, observe=True), deadline_s=4)
    assert "every message follows the schema" in named(findings.failures())


async def test_a_driver_that_never_pairs_fails_at_once() -> None:
    async def silent(_launch: Launch) -> None: ...

    findings = await check_satellite(silent, deadline_s=0.5)
    assert [ENGLISH.format(f.check, "en") for f in findings.failures()] == ["asks to pair"]


async def test_a_driver_without_enrollment_provisioning_is_caught() -> None:
    display_only = Manifest(SPEAKER.device, SPEAKER.capabilities, (PairingMethod.DISPLAY,), software=SOFTWARE)
    findings = await check_satellite(ReferenceSatellite("", display_only), deadline_s=3)
    assert "declares enrollment.provisioning (P1)" in named(findings.failures())
