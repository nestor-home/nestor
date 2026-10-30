from datetime import datetime, timedelta

import pytest

from nestor.core import Capability, ContractError, PersonId, utc_now
from nestor.modules.journal import Journal, LogQuery
from nestor.modules.satellites import (
    Device,
    Manifest,
    Pairing,
    PairingRefused,
    PairingStatus,
    SatellitePaired,
)
from nestor.modules.satellites.types import DeclaredCapability
from nestor.testing.journal import MemoryEventLog

REACHY = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    (DeclaredCapability(Capability("audio.capture")), DeclaredCapability(Capability("expression.emotion"))),
)
MATHIS = PersonId("mathis")


class Clock:
    def __init__(self) -> None:
        self.now = utc_now()

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def pairing(journal: Journal, clock: Clock) -> Pairing:
    pairing = Pairing(journal, clock=clock)
    await pairing.start()
    return pairing


async def _paired(pairing: Pairing, manifest: Manifest = REACHY) -> str:
    ticket = await pairing.request(manifest)
    await pairing.approve(ticket.code, by=MATHIS)
    token = pairing.poll(ticket.id).token
    assert token is not None
    return token


async def test_a_device_approved_by_its_code_gets_a_token_once_and_connects_with_it(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    assert len(ticket.code) == 6 and ticket.code.isdigit()
    assert pairing.poll(ticket.id).status is PairingStatus.PENDING
    assert [p.device for p in pairing.pending()] == [REACHY.device]

    satellite = await pairing.approve(ticket.code, by=MATHIS)
    first, second = pairing.poll(ticket.id), pairing.poll(ticket.id)

    assert first.status is PairingStatus.APPROVED and first.token
    assert (second.status, second.token) == (PairingStatus.CLAIMED, None), "the token is handed out only once"
    assert pairing.authenticate("reachy-salon", first.token) == satellite
    assert (satellite.room, satellite.capabilities) == ("salon", REACHY.names)
    assert not pairing.pending()


async def test_a_wrong_code_approves_nothing(pairing: Pairing) -> None:
    ticket = await pairing.request(REACHY)
    wrong = f"{(int(ticket.code) + 1) % 10**6:06d}"
    with pytest.raises(PairingRefused):
        await pairing.approve(wrong)
    assert pairing.poll(ticket.id).status is PairingStatus.PENDING
    assert not pairing.satellites()


async def test_a_pairing_expires_after_ten_minutes(pairing: Pairing, clock: Clock) -> None:
    ticket = await pairing.request(REACHY)
    clock.now += timedelta(minutes=10)
    with pytest.raises(PairingRefused):
        await pairing.approve(ticket.code)
    assert pairing.poll(ticket.id).status is PairingStatus.EXPIRED
    assert pairing.poll(ticket.id).status is PairingStatus.EXPIRED, "still expired once forgotten"


async def test_an_approved_token_not_claimed_in_time_is_lost(pairing: Pairing, clock: Clock) -> None:
    ticket = await pairing.request(REACHY)
    await pairing.approve(ticket.code)
    clock.now += timedelta(minutes=11)
    assert (pairing.poll(ticket.id).status, pairing.poll(ticket.id).token) == (PairingStatus.EXPIRED, None)


async def test_an_unknown_pairing_reads_as_expired(pairing: Pairing) -> None:
    assert pairing.poll("not-a-pairing").status is PairingStatus.EXPIRED


async def test_a_revoked_satellite_is_refused_even_after_a_restart(pairing: Pairing, journal: Journal) -> None:
    token = await _paired(pairing)
    await pairing.revoke("reachy-salon", by=MATHIS)
    assert pairing.authenticate("reachy-salon", token) is None

    restarted = Pairing(journal)
    await restarted.start()
    assert restarted.authenticate("reachy-salon", token) is None
    with pytest.raises(ContractError):
        await restarted.revoke("reachy-salon")


async def test_paired_satellites_survive_a_restart_and_the_journal_never_holds_a_token(
    pairing: Pairing, journal: Journal
) -> None:
    token = await _paired(pairing)
    restarted = Pairing(journal)
    await restarted.start()
    assert restarted.authenticate("reachy-salon", token) is not None
    records = [entry.record for entry in await journal.log.read(LogQuery())]
    assert records and token not in str(records)


async def test_a_replaced_or_borrowed_token_is_refused(pairing: Pairing) -> None:
    old = await _paired(pairing)
    new = await _paired(pairing)  # paired again: the token is rotated
    assert pairing.authenticate("reachy-salon", old) is None
    assert pairing.authenticate("reachy-salon", new) is not None
    assert pairing.authenticate("enceinte-cuisine", new) is None, "a token only opens its own device"
    assert pairing.authenticate("reachy-salon", "nst1_guessed") is None


async def test_the_approver_can_allow_less_than_the_device_declares(pairing: Pairing, journal: Journal) -> None:
    ticket = await pairing.request(REACHY)
    satellite = await pairing.approve(ticket.code, capabilities=[Capability("audio.capture"), Capability("motion.arm")])
    assert satellite.capabilities == {Capability("audio.capture")}
    [paired] = await journal.history(SatellitePaired)
    assert paired.capabilities == ("audio.capture",)


async def test_asking_again_replaces_the_earlier_code(pairing: Pairing) -> None:
    first = await pairing.request(REACHY)
    second = await pairing.request(REACHY)
    with pytest.raises(PairingRefused):
        await pairing.approve(first.code if first.code != second.code else "-")
    assert pairing.poll(first.id).status is PairingStatus.EXPIRED
    await pairing.approve(second.code)


async def test_too_many_waiting_devices_are_refused(journal: Journal) -> None:
    pairing = Pairing(journal, max_pending=2)
    for i in range(2):
        await pairing.request(Manifest(Device(f"device-{i}", "esp32", "salon")))
    with pytest.raises(PairingRefused):
        await pairing.request(Manifest(Device("device-2", "esp32", "salon")))
